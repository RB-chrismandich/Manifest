---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer identifies generated-output drift, directs the user to check out the run's exact commit and run `make generate`, and inspect `git status`/`git diff` for changed or new generated files. The proposed repair must commit the regenerated artifacts, not weaken or remove the `git diff --exit-code` guard, and it must recommend confirming that the subsequent CI run passes.
