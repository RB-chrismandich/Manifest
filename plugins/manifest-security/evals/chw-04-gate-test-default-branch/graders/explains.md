---
type: llm
focus: last_message
---
- Explains that `issue_comment` (like `workflow_run` and `pull_request_target`) always runs the workflow YAML from the DEFAULT branch, not the PR's copy — so the PR's new gate is inert until merged. GitHub is working as designed.
- Says to test the gate post-merge (or in a fork/test repo with the change on its default branch).
- Bonus (not required): frames this as a security feature, or suggests confirming a non-collaborator comment does not run the job.
Pass if the first two hold.
