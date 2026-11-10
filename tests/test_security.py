"""Regression tests for PDF safety boundaries (no third-party model required)."""
from io import BytesIO
import subprocess

import pytest
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfWriter

from docurisk.isolated import ParseFailed, run_isolated_pdf
from docurisk.pdf_worker import DocumentError, inspect_pdf


def _pdf() -> bytes:
    target = BytesIO()
    c = Canvas(target)
    c.drawString(72, 700, 'The agreement date is January 15, 2025.')
    c.save()
    return target.getvalue()


def test_worker_pdf_inspection(tmp_path):
    doc = tmp_path / 'good.pdf'
    doc.write_bytes(_pdf())
    assert inspect_pdf(doc, max_pages=10) == 1


def test_rejects_fake_pdf_with_magic_header(tmp_path):
    doc = tmp_path / 'bad.pdf'
    doc.write_bytes(b'%PDF-1.7\\nfake')
    with pytest.raises(DocumentError, match='invalid_pdf'):
        inspect_pdf(doc, max_pages=10)


def test_rejects_page_limit(tmp_path):
    doc = tmp_path / 'good.pdf'
    doc.write_bytes(_pdf())
    with pytest.raises(DocumentError, match='page_limit'):
        inspect_pdf(doc, max_pages=0)


def test_rejects_encrypted_pdf(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=400)
    writer.encrypt('password')
    doc = tmp_path / 'encrypted.pdf'
    with doc.open('wb') as handle:
        writer.write(handle)
    with pytest.raises(DocumentError, match='encrypted_pdf'):
        inspect_pdf(doc, max_pages=10)


def test_subprocess_timeout_is_typed_and_does_not_leak_details(tmp_path, monkeypatch):
    upload_dir = tmp_path / 'uploads'
    upload_dir.mkdir()
    doc = upload_dir / 'file.pdf'
    doc.write_bytes(_pdf())
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=['private'], timeout=1)
    monkeypatch.setattr(subprocess, 'run', hang)
    with pytest.raises(ParseFailed, match='parse_timeout'):
        run_isolated_pdf(doc, max_pages=10, max_bytes=20 * 1024 * 1024)


def test_server_does_not_expose_exception_details(tmp_path):
    from fastapi.testclient import TestClient
    from docurisk.api import create_app

    def broken_parser(*args, **kwargs):
        raise RuntimeError('secret contract content must remain private')

    with TestClient(create_app(data_dir=tmp_path, api_key='my-secret-key', parser=broken_parser)) as client:
        response = client.post('/api/v1/documents', headers={'X-API-Key': 'my-secret-key'},
            files={'file': ('contract.pdf', _pdf(), 'application/pdf')})
        assert response.status_code == 202
        metadata = client.get('/api/v1/documents/' + response.json()['document_id'],
            headers={'X-API-Key': 'my-secret-key'}).json()
        assert metadata['status'] == 'failed'
        assert 'secret contract content' not in str(metadata)


def test_sqlite_connections_are_closed(tmp_path, monkeypatch):
    import sqlite3
    import docurisk.storage as storage

    original_connect = sqlite3.connect
    instances = []

    class TrackedConnection(sqlite3.Connection):
        closed = False
        def close(self):
            self.closed = True
            return super().close()

    def connect(*args, **kwargs):
        kwargs['factory'] = TrackedConnection
        conn = original_connect(*args, **kwargs)
        instances.append(conn)
        return conn

    monkeypatch.setattr(storage.sqlite3, 'connect', connect)
    store = storage.Store(tmp_path)
    assert store.get('missing-id') is None
    assert len(instances) >= 2
    assert all(instance.closed for instance in instances)


def test_isolated_worker_accepts_valid_bounded_result(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    upload_dir = tmp_path / 'uploads'
    upload_dir.mkdir()
    pdf = upload_dir / 'file.pdf'
    pdf.write_bytes(_pdf())

    def fake_run(argv, **kwargs):
        assert argv[0]
        assert kwargs['timeout'] > 0
        assert kwargs['check'] is False
        from pathlib import Path
        Path(argv[4]).write_text(json.dumps({'page_count': 1, 'pages': [
            {'page_number': 1, 'text': 'hello', 'markdown': 'hello'}]}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, 'run', fake_run)
    count, pages = run_isolated_pdf(pdf, max_pages=10, max_bytes=20 * 1024 * 1024)
    assert count == 1 and pages[0]['text'] == 'hello'
