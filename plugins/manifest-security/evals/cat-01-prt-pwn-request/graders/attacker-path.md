---
type: llm
focus: last_message
---
- Identifies the pwn-request: `pull_request_target` runs with base-repo secrets/write token, but checks out the fork PR's head SHA and runs `npm ci`/`npm run build` (attacker-controlled package.json scripts/postinstall) with `VERCEL_TOKEN` and a write-all token in reach. Rated high.
- Flags `permissions: write-all` as excessive and recommends least privilege.
- Recommends a structural fix: refuse fork PRs (same-repo check) or split into an unprivileged build job and a privileged deploy job that never runs fork code (e.g. via `workflow_run`/artifact).
- Mentions pinning `actions/checkout` to a full commit SHA (bonus, not required).
Pass only if the first three hold.
