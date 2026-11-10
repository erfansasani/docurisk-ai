"""DocuRisk AI v0.1-alpha: single-user, local-only PDF parsing API.

This is deliberately NOT production-ready multi-tenant contract processing.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile

from docurisk.isolated import ParseFailed, run_isolated_pdf
from docurisk.pdf_worker import inspect_pdf, DocumentError
from docurisk.storage import Store

log = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
CHUNK_SIZE = 1024 * 1024


def create_app(
    *,
    data_dir: Path | None = None,
    api_key: str | None = None,
    parser: Callable[..., list[dict]] | None = None,
) -> FastAPI:
    root = data_dir or Path(os.getenv("DOCURISK_DATA_DIR", "./data"))
    store = Store(root)
    secret = api_key if api_key is not None else os.getenv("DOCURISK_API_KEY", "")

    def authorize(x_api_key: str | None = Header(default=None)) -> None:
        if not secret:
            raise HTTPException(503, "DOCURISK_API_KEY must be configured")
        if x_api_key is None or not secrets.compare_digest(x_api_key, secret):
            raise HTTPException(401, "Invalid API key")

    app = FastAPI(title="DocuRisk AI", version="0.1.0-alpha")

    @app.get("/health/live")
    def health():
        return {"status": "ok"}

    def work(doc_id: str, file_path: Path) -> None:
        store.set_status(doc_id, "running")
        try:
            if parser is None:
                count, pages = run_isolated_pdf(
                    file_path, max_pages=MAX_PAGES, max_bytes=MAX_UPLOAD_BYTES
                )
            else:
                # Dependency injection is for deterministic unit tests only.
                count = inspect_pdf(file_path, max_pages=MAX_PAGES)
                pages = parser(file_path, max_pages=MAX_PAGES, max_bytes=MAX_UPLOAD_BYTES)
            if len(pages) != count:
                raise ParseFailed()
            store.complete(doc_id, pages, count)
        except (ParseFailed, DocumentError) as exc:
            log.warning("PDF job failed: id=%s code=%s", doc_id, exc.code)
            store.set_status(doc_id, "failed", exc.code)
        except Exception:
            # Never print arbitrary parser exception text containing contract data.
            log.error("PDF job failed unexpectedly: id=%s", doc_id)
            store.set_status(doc_id, "failed", "parse_failed")

    @app.post("/api/v1/documents", status_code=202, dependencies=[Depends(authorize)])
    async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(415, "Only PDF files are supported")
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(415, "Only PDF files are supported")

        doc_id = str(uuid4())
        target = store.uploads / f"{doc_id}.pdf"
        digest = hashlib.sha256()
        byte_count = 0
        try:
            with target.open("xb") as output:
                while data := await file.read(CHUNK_SIZE):
                    byte_count += len(data)
                    if byte_count > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "PDF exceeds 20 MB limit")
                    digest.update(data)
                    output.write(data)
            with target.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise HTTPException(415, "Invalid PDF signature")
            store.add({
                "id": doc_id,
                "filename": Path(file.filename).name,
                "sha256": digest.hexdigest(),
                "size_bytes": byte_count,
                "page_count": 0,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            background_tasks.add_task(work, doc_id, target)
            return {"document_id": doc_id, "status": "queued", "page_count": None}
        except Exception:
            if target.exists():
                target.unlink()
            raise
        finally:
            await file.close()

    @app.get("/api/v1/documents/{document_id}", dependencies=[Depends(authorize)])
    def get_document(document_id: str):
        doc = store.get(document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        return doc

    @app.get("/api/v1/documents/{document_id}/pages/{page_number}", dependencies=[Depends(authorize)])
    def get_page(document_id: str, page_number: int):
        doc = store.get(document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        if doc["status"] != "completed":
            raise HTTPException(409, "Document is not ready")
        page = store.page(document_id, page_number)
        if page is None:
            raise HTTPException(404, "Page not found")
        return page

    @app.delete("/api/v1/documents/{document_id}", status_code=204, dependencies=[Depends(authorize)])
    def delete_document(document_id: str):
        # Avoid removing uploads while a background task is still processing.
        doc = store.get(document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        if doc["status"] in ("queued", "running"):
            raise HTTPException(409, "Wait until document processing finishes")
        store.delete(document_id)
        (store.uploads / f"{document_id}.pdf").unlink(missing_ok=True)

    return app


app = create_app()
