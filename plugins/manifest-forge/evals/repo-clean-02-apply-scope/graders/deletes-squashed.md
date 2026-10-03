---
type: llm
focus: last_message
weight: 1
---
Pass if the command list deletes local feat/billing and feat/ui-tweak, justified by their squash-merged PRs. `git branch -D` is acceptable here because the fixture states each branch tip equals the merged PR head (no commits added after the merge); optional pre-checks like `git cherry`/`git log` comparisons are also fine. Fail if it deletes either branch without referencing the squash-merged PR evidence at all.
