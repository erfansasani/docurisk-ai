"""Docling adapter: English born-digital PDFs only (OCR intentionally disabled)."""
from pathlib import Path


def parse_pdf(path: Path, *, max_pages: int, max_bytes: int) -> list[dict]:
    """Return per-page plain text and Markdown; raise on conversion failure.

    Docling is an optional heavy dependency so unit tests can run without its models.
    Install docurisk-ai[docling] for actual document processing.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)},
    )
    result = converter.convert(path, max_num_pages=max_pages, max_file_size=max_bytes)
    try:
        doc = result.document
        pages = [
            {
                "page_number": number,
                "text": doc.export_to_text(page_no=number),
                "markdown": doc.export_to_markdown(page_no=number),
            }
            for number in sorted(doc.pages)
        ]
        if not pages or not any(page["text"].strip() for page in pages):
            raise ValueError("No extractable text found; scanned PDFs are not supported")
        return pages
    finally:
        # Docling retains PDF backend handles until explicitly released.
        result.input.release()
