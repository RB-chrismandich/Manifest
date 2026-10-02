---
type: llm
focus: last_message
---
- Recommends a CODEOWNERS entry covering `/.github/workflows/` AND the allowlist file.
- Recommends branch protection (or rulesets) on the default branch requiring PR review and "Require review from Code Owners", plus dismiss stale reviews and blocking force-push/deletion (at least two of these).
- Addresses the sole-maintainer lockout: e.g. `enforce_admins: false` under classic protection or a ruleset bypass actor for the owner.
- Notes that comment/workflow_run-triggered workflows execute the default-branch copy, so an unmerged PR editing the gate is inert until merged — OR that a file checked out from the PR head at runtime is a separate vector.
Pass if the first three hold (fourth is a bonus).
