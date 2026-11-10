import sys
import types

from docurisk.parser import parse_pdf


def test_parser_calls_docling_and_preserves_page_numbers(monkeypatch, tmp_path):
    class PDFDoc:
        pages = {1: object(), 2: object()}
        def export_to_text(self, *, page_no):
            return f"text-{page_no}"
        def export_to_markdown(self, *, page_no):
            return f"# page-{page_no}"

    class Input:
        released = False
        def release(self):
            self.released = True

    class Converter:
        def __init__(self, **kwargs):
            pass
        def convert(self, path, **kwargs):
            assert kwargs["max_num_pages"] == 100
            return types.SimpleNamespace(document=PDFDoc(), input=Input())

    packages = {
        "docling": types.ModuleType("docling"),
        "docling.datamodel": types.ModuleType("docling.datamodel"),
        "docling.datamodel.base_models": types.SimpleNamespace(InputFormat=types.SimpleNamespace(PDF="pdf")),
        "docling.datamodel.pipeline_options": types.SimpleNamespace(PdfPipelineOptions=lambda **kwargs: kwargs),
        "docling.document_converter": types.SimpleNamespace(DocumentConverter=Converter, PdfFormatOption=lambda **kwargs: kwargs),
    }
    for key, value in packages.items():
        monkeypatch.setitem(sys.modules, key, value)
    result = parse_pdf(tmp_path / "dummy.pdf", max_pages=100, max_bytes=2000)
    assert result == [
        {"page_number": 1, "text": "text-1", "markdown": "# page-1"},
        {"page_number": 2, "text": "text-2", "markdown": "# page-2"},
    ]
