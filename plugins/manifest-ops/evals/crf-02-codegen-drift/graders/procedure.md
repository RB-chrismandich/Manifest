---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It identifies this as generated-artifact drift: the committed generated files are out of sync with their source.
2. It says to run `make generate` locally (at the run's commit) and inspect `git status`/`git diff` for changed or new untracked generated files.
3. The fix it recommends is committing the regenerated output, NOT weakening/removing the `git diff --exit-code` check.
4. It recommends confirming the fresh CI run actually passes after pushing.
