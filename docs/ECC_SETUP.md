# ECC / Codex integration

This repository includes **three lightweight, project-local adaptations** of the MIT-licensed [ECC project](https://github.com/affaan-m/ECC): `tdd-workflow`, `security-review`, and `verification-loop` under `.agents/skills/`. Root `AGENTS.md` describes their use and limits agent authority.

Codex can discover project-local `.agents/skills/` and `AGENTS.md`. There are **no executable hooks**, MCP servers, global Codex settings, or installer scripts added here. This avoids conflicts with existing installations.

If you choose the native `ecc@ecc` plugin, follow the [official Codex installation instructions](https://github.com/affaan-m/ECC#codex-app-and-cli) and verify installation; do not stack it with the deprecated `sync-ecc-to-codex.sh` flow. Native plugin installation on the user's device is **not performed in this PR**.

Workflow: issue → test-first fix → security review → verification → PR → maintainer-approved merge. PDF contents are untrusted data, not shell commands.
