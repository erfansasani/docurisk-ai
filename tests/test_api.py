from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas

from docurisk.api import create_app


def valid_pdf() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 750, "This agreement begins on 1 January 2025.")
    canvas.save()
    return stream.getvalue()


@pytest.fixture
def client(tmp_path):
    def fake_parser(path, *, max_pages, max_bytes):
        assert path.is_file()
        assert max_pages == 100
        return [{"page_number": 1, "text": "This agreement begins", "markdown": "This agreement begins"}]

    with TestClient(create_app(data_dir=tmp_path, api_key="test-key", parser=fake_parser)) as test_client:
        yield test_client


def headers():
    return {"X-API-Key": "test-key"}


def test_full_lifecycle(client):
    response = client.post(
        "/api/v1/documents", headers=headers(),
        files={"file": ("agreement.pdf", valid_pdf(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["document_id"]
    meta = client.get(f"/api/v1/documents/{document_id}", headers=headers())
    assert meta.status_code == 200
    assert meta.json()["status"] == "completed"
    assert meta.json()["page_count"] == 1
    page = client.get(f"/api/v1/documents/{document_id}/pages/1", headers=headers())
    assert page.json()["text"] == "This agreement begins"
    assert client.get(f"/api/v1/documents/{document_id}/pages/2", headers=headers()).status_code == 404
    assert client.delete(f"/api/v1/documents/{document_id}", headers=headers()).status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}", headers=headers()).status_code == 404


def test_rejects_unauthorized(client):
    assert client.get("/api/v1/documents/random").status_code == 401
    assert client.post("/api/v1/documents", files={"file": ("a.pdf", valid_pdf(), "application/pdf")}).status_code == 401


@pytest.mark.parametrize("filename,data,mime,expected", [
    ("wrong.txt", b"hello", "text/plain", 415),
    ("malformed.pdf", b"not-a-pdf", "application/pdf", 415),
])
def test_rejects_invalid_files(client, filename, data, mime, expected):
    response = client.post("/api/v1/documents", headers=headers(), files={"file": (filename, data, mime)})
    assert response.status_code == expected


def test_parser_failure_is_visible(tmp_path):
    def failing_parser(*args, **kwargs):
        raise ValueError("sensitive internal parse details")
    with TestClient(create_app(data_dir=tmp_path, api_key="test-key", parser=failing_parser)) as client:
        response = client.post("/api/v1/documents", headers=headers(), files={"file": ("a.pdf", valid_pdf(), "application/pdf")})
        doc_id = response.json()["document_id"]
        meta = client.get(f"/api/v1/documents/{doc_id}", headers=headers()).json()
        assert meta["status"] == "failed"
        assert meta["error_code"] == "parse_failed"
        assert "sensitive" not in str(meta)


def test_malformed_pdf_valid_signature_fails_as_background_job(client):
    # Expensive PDF inspection must not run in the async upload endpoint.
    response = client.post(
        '/api/v1/documents', headers=headers(),
        files={'file': ('malformed.pdf', b'%PDF-1.7\\nnot a valid pdf', 'application/pdf')},
    )
    assert response.status_code == 202
    doc_id = response.json()['document_id']
    metadata = client.get(f'/api/v1/documents/{doc_id}', headers=headers()).json()
    assert metadata['status'] == 'failed'
    assert metadata['error_code'] in ('invalid_pdf', 'parse_failed')


def test_valid_pdf_is_never_parsed_in_upload_event_loop(tmp_path, monkeypatch):
    # Heavy PDF inspection is deferred to the worker thread.
    import docurisk.pdf_worker as pdf_worker
    calls = []
    original = pdf_worker.PdfReader
    def probe(*args, **kwargs):
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            calls.append('worker')
        else:
            calls.append('event_loop')
        return original(*args, **kwargs)
    monkeypatch.setattr(pdf_worker, 'PdfReader', probe)
    with TestClient(create_app(data_dir=tmp_path, api_key='test-key', parser=lambda *a, **kw: [
        {'page_number': 1, 'text': 'test', 'markdown': 'test'}
    ])) as client:
        response = client.post('/api/v1/documents', headers=headers(),
            files={'file': ('a.pdf', valid_pdf(), 'application/pdf')})
        assert response.status_code == 202
    assert 'event_loop' not in calls
