---
type: llm
focus: last_message
---
- Explains the gate authenticates the COMMENTER, not the PR/code author: a maintainer typing /deploy on an outsider's fork PR runs the fork's `scripts/deploy.sh` with AWS secrets (pwn-request).
- Explains `author_association` is not a write-access check (COLLABORATOR can include read/triage-only; MEMBER is any org member) and suggests verifying actual permission (e.g. collaborators/{user}/permission → admin/write).
- Recommends refusing fork PRs / same-repo check, or not executing checked-out PR code in the secret-bearing job.
Pass only if all three hold.
