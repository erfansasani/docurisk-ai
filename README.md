# DocuRisk AI

**Status:** v0.1.0-alpha source scaffold (not yet a GitHub Release). English-first local PDF parsing API with Docling integration. This is the foundation for evidence-grounded contract intelligence; it is **not** a contract risk classifier or legal-advice product yet.

## What works in this alpha

- Accepts **born-digital English PDF** uploads (max 20 MB, 1–100 pages). Rejects encrypted, malformed and image-only/scanned PDFs.
- Saves PDFs in a private local volume and stores document metadata/status plus extracted per-page text and Markdown in SQLite.
- Runs Docling parsing after a 202 Accepted upload response, in a FastAPI background task.
- Exposes authenticated status, per-page results and deletion endpoints (X-API-Key).
- Has automated API tests and a mocked Docling adapter test.

**Not implemented:** OCR/Persian extraction, multi-user authorization, clauses, RAG, AI analysis, citations/bounding boxes, risk assessment, durable job queue, web frontend. Those are tracked in the repository Issues (#2–#19).

## Run locally

Docling may download model assets on its first run; the Docker build/install is comparatively large.

~~~bash
cp .env.example .env
# Replace DOCURISK_API_KEY in .env with a strong secret
# Example: python -c 'import secrets; print(secrets.token_urlsafe(48))'
docker compose up --build
~~~

The API is bound to **127.0.0.1:8000** (not a public interface). See the OpenAPI reference at http://127.0.0.1:8000/docs.

~~~bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H 'X-API-Key: YOUR_SECRET' \
  -F 'file=@agreement.pdf;type=application/pdf'
# {"document_id":"...","status":"queued","page_count":1}

curl -H 'X-API-Key: YOUR_SECRET' \
  http://127.0.0.1:8000/api/v1/documents/DOCUMENT_ID

curl -H 'X-API-Key: YOUR_SECRET' \
  http://127.0.0.1:8000/api/v1/documents/DOCUMENT_ID/pages/1
~~~

Status may be queued, running, completed or failed. Parsing happens after the HTTP response; poll the status endpoint before fetching pages.

## Run tests without installing the Docling model

~~~bash
python -m pip install -e '.[test]'
python -m pytest -q
~~~

The CI suite stubs the expensive parser. **A real end-to-end Docling conversion and Docker image build must be validated separately** before shipping or claiming a working release.

## Architecture and constraints

FastAPI -> SQLite metadata -> background Docling parser -> per-page text/Markdown.

- The initial endpoint uses a single configurable API key, **not multi-tenant auth**. Do not expose it to the internet or upload confidential contracts yet.
- FastAPI background tasks are **not a durable queue**. A process crash can leave a job in a pending state; the intended replacement is Celery/Redis (see #5).
- Uploaded PDFs and extracted content remain in the Docker named volume until deleted. Never commit real contracts or credentials.
- OCR is disabled; reading English text-based PDFs is the goal of this alpha.
- For future Persian support, the data layer will keep raw strings and separate normalized values and language-specific indexing. Current extraction support is English only.

## Roadmap

See [GitHub Issues](https://github.com/erfansasani/docurisk-ai/issues): structured data and provenance, CUAD evaluation, evidence-grounded retrieval, Persian support and contract-analysis features.

## Limitations

This prototype has not been security audited. It does not determine whether a clause is legally enforceable. There are no measured clause-extraction benchmarks yet; those must come from proper validation on held-out datasets such as CUAD.
