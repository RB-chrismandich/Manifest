---
type: llm
focus: last_message
---
- Adds a gate so it only deploys when the triggering run succeeded AND came from the base repo / default branch (e.g. `workflow_run.conclusion == 'success'`, `head_repository.full_name == github.repository`, `head_branch == 'main'`), explaining that fork PR CI runs can trigger workflow_run.
- Sets explicit least-privilege `permissions:`.
- Moves the prod secret behind a GitHub Environment (optionally with required reviewers) via `environment:`.
- Checks out and deploys the exact commit CI tested (`ref: ${{ github.event.workflow_run.head_sha }}` or equivalent), not a branch name or the default ref.
- SHA-pins `actions/checkout` and `some-org/deploy-action` (for the fictional deploy action, a clearly marked placeholder such as `@<full-commit-sha>` with verification instructions is acceptable; a specific invented SHA is NOT), and warns that passing untrusted `head_branch` into the action's `with:` can re-create injection if the action inline-templates inputs (sanitize/allowlist the branch, or pass the SHA instead).
Pass only if all five hold.
