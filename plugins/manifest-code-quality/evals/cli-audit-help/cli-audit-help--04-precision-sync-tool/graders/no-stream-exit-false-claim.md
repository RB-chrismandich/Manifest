---
type: llm
weight: 0.5
---
Score 1 if the answer does not incorrectly claim that the usage text is written to the wrong stream or that the exit code for `--help` is wrong (it correctly goes to stdout via `cat` inside `usage`, then `exit 0`). Score 0 if it fabricates a stream/exit-code bug for the help path.
