"""Bounded child-process runner for untrusted PDF parsing."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_RESULT_BYTES = 30 * 1024 * 1024
PARSE_TIMEOUT_SECONDS = 120


class ParseFailed(ValueError):
    def __init__(self, code='parse_failed'):
        super().__init__(code)
        self.code = code


def run_isolated_pdf(path: Path, *, max_pages: int, max_bytes: int) -> tuple[int, list[dict]]:
    # Paths are UUID-generated and only data from the app's private volume.
    with tempfile.TemporaryDirectory(prefix='docurisk-parse-', dir=path.parent.parent) as directory:
        result_file = Path(directory) / 'result.json'
        try:
            run = subprocess.run(
                [sys.executable, '-m', 'docurisk.pdf_worker', str(path), str(result_file),
                 str(max_pages), str(max_bytes)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PARSE_TIMEOUT_SECONDS + 5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ParseFailed('parse_timeout') from exc
        if run.returncode != 0 or not result_file.is_file():
            raise ParseFailed()
        if result_file.stat().st_size > MAX_RESULT_BYTES:
            raise ParseFailed('result_limit')
        try:
            result = json.loads(result_file.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise ParseFailed() from exc
        if 'error_code' in result:
            raise ParseFailed(result['error_code'])
        pages, count = result.get('pages'), result.get('page_count')
        if not isinstance(pages, list) or not isinstance(count, int) or len(pages) != count:
            raise ParseFailed()
        return count, pages
