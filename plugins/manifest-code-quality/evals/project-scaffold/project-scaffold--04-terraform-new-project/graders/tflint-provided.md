---
type: llm
focus: trace
weight: 1
---
The eval harness may block writing dotfiles, so `.tflint.hcl` may not be writable in this run. Score 1 only if EITHER a Write/Edit/Bash call in the trace successfully created `.tflint.hcl`, OR the final answer shows its full intended contents (a TFLint configuration) and clearly states the file could not be written. Score 0 if the TFLint config is silently omitted, or the answer claims it was created when the write failed.
