---
name: tdd-workflow
description: ECC-aligned test-first workflow for changes to DocuRisk's Python API, parsing, or storage code.
---
# Test-driven development (adapted from ECC)
Source: https://github.com/affaan-m/ECC/tree/main/skills/tdd-workflow (MIT).

## Activate
On bug fixes, new APIs, parser integration, and security changes.

## Steps
1. Define a measurable user behavior and a failing test.
2. Run it: confirm RED is caused by the targeted bug, not missing dependencies.
3. Make the smallest code change; rerun to GREEN.
4. Run all lightweight tests with `python -m pytest -q`.
5. Run the real Docling test separately; stubs do not establish model compatibility.
6. Record RED/GREEN evidence and limitations in the PR.

## Anti-patterns
Never bypass implementation with a mock of the feature under test. Never report unexecuted Docker or Docling tests as passing.
