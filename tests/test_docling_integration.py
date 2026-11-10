"""Real Docling smoke test: only run in dedicated CI job with docling installed."""
from io import BytesIO

import pytest
from reportlab.pdfgen.canvas import Canvas

from docurisk.isolated import run_isolated_pdf
from docurisk.parser import parse_pdf

pytestmark = pytest.mark.docling_integration


def test_real_pdf_conversion_with_docling(tmp_path):
    pytest.importorskip('docling')
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 740, 'SERVICE AGREEMENT')
    canvas.drawString(72, 710, 'Effective date is January 15, 2025.')
    canvas.save()
    pdf_file = tmp_path / 'sample.pdf'
    pdf_file.write_bytes(buffer.getvalue())
    # Direct path first: if Docling itself fails, CI reports the real traceback.
    direct_pages = parse_pdf(pdf_file, max_pages=10, max_bytes=20 * 1024 * 1024)
    assert len(direct_pages) == 1
    # Then verify the security boundary that invokes the same parser in a subprocess.
    count, pages = run_isolated_pdf(pdf_file, max_pages=10, max_bytes=20 * 1024 * 1024)
    assert count == 1
    assert len(pages) == 1
    assert pages[0]['page_number'] == 1
    assert 'SERVICE AGREEMENT' in pages[0]['text']
    assert 'January 15, 2025' in pages[0]['markdown']
