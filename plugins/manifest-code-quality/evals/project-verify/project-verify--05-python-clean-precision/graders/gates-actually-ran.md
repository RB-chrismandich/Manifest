---
type: llm
focus: trace
weight: 1
---
The verdict must come from real tool runs, not inference from the prompt. Score 1 only if, AFTER the project files were written, the trace shows Bash calls that actually executed `ruff` (e.g. `ruff check .`) and `pytest` (or `python3 -m pytest`) against the project, AND the final verdict's cited failures/passes match what those runs output. A run that could not execute (tool missing, permission denied) counts only if the answer reports it as not run rather than as a pass or fail. Score 0 if no lint/test command was executed, or if the verdict asserts results that no executed command produced.
