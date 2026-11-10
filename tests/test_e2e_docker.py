"""Real, external-HTTP E2E checks against the API running inside Docker.

The document fixture is synthetic; no user credentials or private PDFs are needed.
Run only with DOCURISK_E2E_BASE_URL and DOCURISK_API_KEY configured.
"""
import hashlib
import os
import time
from io import BytesIO
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import pytest
from reportlab.pdfgen import canvas

pytestmark = pytest.mark.docker_e2e

TERMINAL_STATES = {"completed", "failed"}


def synthetic_contract() -> bytes:
    """Create two born-digital PDF pages entirely in memory."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 730, "DOCURISK E2E SERVICE AGREEMENT")
    pdf.drawString(72, 700, "Effective date: January 15, 2025.")
    pdf.showPage()
    pdf.drawString(72, 730, "CONFIDENTIALITY AND DATA USE")
    pdf.drawString(72, 700, "Parties shall protect confidential information.")
    pdf.save()
    return buffer.getvalue()


@pytest.fixture(scope="module")
def live_api():
    base_url = os.getenv("DOCURISK_E2E_BASE_URL", "").rstrip("/")
    api_key = os.getenv("DOCURISK_API_KEY", "")
    parsed = urlsplit(base_url)

    # Avoid accidentally uploading fixtures to an arbitrary or production host.
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        pytest.fail("E2E requires an explicit local HTTP DOCURISK_E2E_BASE_URL")
    if not api_key or api_key == "REPLACE_WITH_LONG_RANDOM_SECRET":
        pytest.fail("Provide an ephemeral DOCURISK_API_KEY for E2E")
    headers = {"X-API-Key": api_key}

    with httpx.Client(base_url=base_url, timeout=30.0, trust_env=False) as client:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                response = client.get("/health/live")
                if response.status_code == 200 and response.json().get("status") == "ok":
                    break
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(1)
        else:
            pytest.fail("Docker API did not become healthy within 90 seconds")
        yield client, headers


def wait_for_terminal(client: httpx.Client, headers: dict, document_id: str) -> dict:
    deadline = time.monotonic() + 180
    observed = set()
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/documents/{document_id}", headers=headers)
        assert response.status_code == 200, f"document status endpoint: {response.status_code}"
        metadata = response.json()
        state = metadata["status"]
        observed.add(state)
        assert state in {"queued", "running", "completed", "failed"}
        if state in TERMINAL_STATES:
            return metadata
        time.sleep(2)
    pytest.fail(f"Processing never reached a terminal state; states={sorted(observed)}")


def test_document_lifecycle_with_real_docling(live_api):
    client, headers = live_api
    pdf_bytes = synthetic_contract()

    # This is a real multipart POST to the container, not TestClient or a stubbed parser.
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("synthetic-agreement.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    accepted = response.json()
    document_id = str(UUID(accepted["document_id"]))
    assert accepted["status"] == "queued"
    assert accepted["page_count"] is None

    metadata = wait_for_terminal(client, headers, document_id)
    assert metadata["status"] == "completed", (
        f"Document failed to parse: {metadata.get('error_code')}"
    )
    assert metadata["page_count"] == 2
    assert metadata["size_bytes"] == len(pdf_bytes)
    assert metadata["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()

    first = client.get(f"/api/v1/documents/{document_id}/pages/1", headers=headers)
    second = client.get(f"/api/v1/documents/{document_id}/pages/2", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["page_number"] == 1
    assert second.json()["page_number"] == 2
    assert "SERVICE AGREEMENT" in first.json()["text"]
    assert "January 15, 2025" in first.json()["text"]
    assert "CONFIDENTIALITY AND DATA USE" in second.json()["text"]
    assert "protect confidential information" in second.json()["text"]
    assert "CONFIDENTIALITY AND DATA USE" not in first.json()["text"]

    not_found = client.get(f"/api/v1/documents/{document_id}/pages/3", headers=headers)
    assert not_found.status_code == 404

    deleted = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}", headers=headers).status_code == 404
    assert client.get(
        f"/api/v1/documents/{document_id}/pages/1", headers=headers
    ).status_code == 404


def test_authentication_and_upload_validation_over_http(live_api):
    client, headers = live_api
    assert client.get("/api/v1/documents/nonexistent").status_code == 401
    assert client.get(
        "/api/v1/documents/nonexistent", headers={"X-API-Key": "incorrect-key"}
    ).status_code == 401
    assert client.get(
        "/api/v1/documents/nonexistent", headers=headers
    ).status_code == 404

    bad_content = client.post(
        "/api/v1/documents", headers=headers,
        files={"file": ("fake.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert bad_content.status_code == 415
    bad_extension = client.post(
        "/api/v1/documents", headers=headers,
        files={"file": ("not-pdf.txt", b"hello", "text/plain")},
    )
    assert bad_extension.status_code == 415


def test_malformed_pdf_reports_safe_background_failure(live_api):
    client, headers = live_api
    corrupted = b"%PDF-1.7\nnot a real document\n"
    result = client.post(
        "/api/v1/documents", headers=headers,
        files={"file": ("corrupted.pdf", corrupted, "application/pdf")},
    )
    assert result.status_code == 202
    doc_id = str(UUID(result.json()["document_id"]))
    metadata = wait_for_terminal(client, headers, doc_id)
    assert metadata["status"] == "failed"
    assert metadata["error_code"] in {"invalid_pdf", "parse_failed"}
    assert "not a real document" not in str(metadata)
    assert client.delete(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 204
