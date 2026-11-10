# Security and execution review — v0.1.0-alpha

## Findings addressed in this PR

- **Request event-loop blocking:** Previously `pypdf.PdfReader` and text extraction ran in `POST /documents`. Upload now performs bounded streaming and a minimal `%PDF-` header check; page inspection and Docling conversion happen only after HTTP 202.
- **Unbounded parsing:** Production-path conversion runs in a child process with wall timeout and Linux CPU/file-size limits. Timeouts terminate the child, return safe error codes and avoid exposing raw exception messages.
- **Docker attack surface:** `.dockerignore` excludes secrets/data; non-root container, localhost bind, read-only root, tmpfs, dropped capabilities, no-new-privileges and bounded memory/PIDs/CPU.
- **SQLite file descriptor leakage:** Connections are now explicitly closed in a transaction-aware context manager, with a regression test.
- **Mock-only coverage:** Dedicated GitHub Actions jobs for actual Docling extraction and Docker build/import, separate from fast unit tests.

## Residual risks: not production-ready

- FastAPI BackgroundTasks is not durable; jobs can be lost during restarts. Celery/Redis and recoverable state are future work.
- A child process is **not a full PDF sandbox**: it still shares container networking and mounted volumes. Sensitive workloads require separate network-restricted worker, malware checks and stronger OS confinement.
- SQLite + one API key are for local evaluation only; workspace isolation, storage encryption, rate limiting and retention policies remain outstanding.
- Real documents may be rejected by strict PDF inspection; evaluate false rejections and resource limits on safe fixtures.
- Docling model assets may download at runtime; pin/prefetch them before production deployment.
- Verify real Docling and Docker CI outcomes on the PR; local mocked tests cannot prove those integrations work.
