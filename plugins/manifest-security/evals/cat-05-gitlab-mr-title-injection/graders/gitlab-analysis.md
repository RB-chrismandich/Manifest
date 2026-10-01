---
type: llm
focus: last_message
---
- Flags that `$CI_MERGE_REQUEST_TITLE` (attacker-controlled by a fork MR author) is passed through `eval`, enabling command injection with `RELEASE_BOT_TOKEN` in scope. Rated high.
- Notes that running fork MR pipelines in the parent project exposes parent-project variables, and that `RELEASE_BOT_TOKEN` should be a protected (and masked) variable only available on protected branches/tags.
- Uses GitLab concepts (protected variables/branches, fork MR pipelines), not GitHub-only advice like author_association or pull_request_target.
Pass only if all three hold.
