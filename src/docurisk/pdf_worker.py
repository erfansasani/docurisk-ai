"""Isolated PDF parser entry point. Accept only a server-created file path.

Runs in a separate OS process so an unresponsive parser can be terminated by
its parent. This is not a replacement for container/sandbox isolation.
"""
import json
import os
import sys
from pathlib import Path

from pypdf import PdfReader

from docurisk.parser import parse_pdf


class DocumentError(ValueError):
    """An invalid/unsupported PDF with a safe public error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def inspect_pdf(path: Path, *, max_pages: int) -> int:
    try:
        with path.open('rb') as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                raise DocumentError('encrypted_pdf')
            count = len(reader.pages)
            if not 1 <= count <= max_pages:
                raise DocumentError('page_limit')
            # Quick born-digital gate; real extraction is done by Docling.
            if not any(bool((page.extract_text() or '').strip()) for page in reader.pages):
                raise DocumentError('scanned_pdf')
            return count
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError('invalid_pdf') from exc


def inspect_and_parse(path: Path, *, max_pages: int, max_bytes: int) -> tuple[int, list[dict]]:
    count = inspect_pdf(path, max_pages=max_pages)
    pages = parse_pdf(path, max_pages=max_pages, max_bytes=max_bytes)
    if not pages or len(pages) != count:
        raise DocumentError('parse_failed')
    if [page['page_number'] for page in pages] != list(range(1, count + 1)):
        raise DocumentError('parse_failed')
    return count, pages


def _apply_limits() -> None:
    # Apply in the child process to avoid unsafe preexec_fn in threaded servers.
    if os.name != 'posix':
        return
    import resource
    max_cpu = 120
    for kind, desired in [
        (resource.RLIMIT_CPU, max_cpu),
        (resource.RLIMIT_FSIZE, 30 * 1024 * 1024),
    ]:
        soft, hard = resource.getrlimit(kind)
        bounded = min(desired, hard) if hard != resource.RLIM_INFINITY else desired
        resource.setrlimit(kind, (bounded, hard))


def main() -> int:
    # Only called by docurisk.api with private temporary output, not user input.
    _apply_limits()
    if len(sys.argv) != 5:
        return 2
    input_path, output_path, max_pages, max_bytes = sys.argv[1:]
    try:
        count, pages = inspect_and_parse(
            Path(input_path), max_pages=int(max_pages), max_bytes=int(max_bytes)
        )
        payload = {'page_count': count, 'pages': pages}
    except DocumentError as exc:
        payload = {'error_code': exc.code}
    except Exception:
        # Never serialize arbitrary exception messages or PDF content into logs.
        payload = {'error_code': 'parse_failed'}
    Path(output_path).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
