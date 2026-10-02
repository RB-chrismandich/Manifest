---
type: llm
focus: trace
weight: 0.5
---
The skill requires verifying edits before reporting success. Score 1 only if, AFTER the last edit to the code under audit, the trace shows at least one executed verification: the constitution checker (`constitution_check.py`), the project's tests (`pytest`), or at minimum an import/compile/run check of the edited files (e.g. `python3 -c "import ..."`, `python3 -m py_compile ...`). For a case where the correct outcome is no edits, verifying the original file counts. Score 0 if no verification command was run after editing, or if the final message claims verification that the trace does not show.
