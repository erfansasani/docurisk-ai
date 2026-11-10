---
name: verification-loop
description: ECC-aligned pre-PR checklist for tests, security and real target-environment acceptance.
---
# Verification loop (adapted from ECC)
Source: https://github.com/affaan-m/ECC/tree/main/skills/verification-loop (MIT).

## Activate
After implementation and before asking for PR review.

## Gates
1. Compile: `python -m compileall -q src tests`.
2. Unit/security tests: `python -m pytest -q`.
3. Real Docling: `python -m pytest -q -o addopts= tests/test_docling_integration.py` with models.
4. Docker: `docker compose config`, `docker build`, import smoke test.
5. Security review: secrets, upload validation, subprocess and container isolation, diff.
6. Ensure changes are confined to the approved repo/branch. Do not merge.

## Report
For each gate, report PASS, FAIL or NOT RUN with environment and evidence. Distinguish mocks from real integration. State residual risks.
