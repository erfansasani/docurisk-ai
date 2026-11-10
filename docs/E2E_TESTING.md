# Docker end-to-end testing

The **E2E check** covers the complete public API journey from an external HTTP client through the running Docker container (FastAPI → background task → real Docling subprocess → SQLite) and back to HTTP.

## Why this is different

- Unit tests use a stubbed parser for speed and deterministic error checks.
- The Docling integration test processes a PDF but does not exercise a live HTTP server.
- The Docker smoke test checks that an image builds and imports.
- **This E2E test** sends actual HTTP requests to Docker, uploads a synthetic two-page PDF, polls for completion, checks both page texts and SHA-256, then verifies deletion. It also tests authentication, invalid uploads and a corrupt PDF's safe error response.

## Automated CI

The `docker-build` GitHub Actions job builds the real image, starts it through `docker compose`, creates a disposable random API key for that CI run, and executes `tests/test_e2e_docker.py` against `http://127.0.0.1:8000`. An `always()` cleanup step runs `docker compose down -v` so generated PDFs and the SQLite test database are removed. E2E tests have no access to user secrets or confidential files.

The Docker job runs on pull requests, pushes to main, and manual workflow dispatches. The default fast unit suite explicitly **excludes** `docker_e2e` and `docling_integration`; each has a dedicated CI invocation.

## Local reproduction

Use **test-only local** data and a temporary API key. Never connect this test to a public deployment or use customer PDFs.

~~~bash
python -m pip install -e '.[test]'
export DOCURISK_API_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DOCURISK_E2E_BASE_URL=http://127.0.0.1:8000

# With Docker installed:
docker compose -p docurisk-e2e up -d --build
python -m pytest -q -o addopts='' tests/test_e2e_docker.py
docker compose -p docurisk-e2e down -v --remove-orphans
~~~

**Important:** The compose service binds only to localhost. `down -v` destroys the **docurisk-e2e project test volume**, so do not reuse that Compose project name for any personal data.

## Expected results and troubleshooting

- **Success:** 3 E2E scenarios succeed, including a real two-page document lifecycle and safe handling of corrupted input.
- **API does not start:** check Docker startup, volume permissions and health endpoint.
- **Job stays queued/running:** FastAPI background tasks are not a durable queue; inspect the test container and failure states.
- **Docling fails:** check model downloads, available memory, native dependencies and subprocess timeout.
- **Missing PDF text:** examine page mapping, PDF format and Docling version.
- **Failure cleanup:** CI still runs `docker compose down -v`. We do not print confidential content or tokens.

This is an alpha development gate, not a load test or a production-security certification. Rate limiting, network isolation, workspace authorization and retryable workers remain future work.

## ECC review gates

Plan → define lifecycle acceptance criteria → add an E2E test that exercises real components → run in CI → inspect failures and correct only within the approved scope → security check → open Pull Request. No merge without owner approval.

Related: [DR-06](https://github.com/erfansasani/docurisk-ai/issues/6), [DR-18](https://github.com/erfansasani/docurisk-ai/issues/18).
