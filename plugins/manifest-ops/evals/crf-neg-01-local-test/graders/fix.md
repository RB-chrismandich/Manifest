---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It diagnoses the src-layout import problem and gives a concrete fix (e.g. `pip install -e .`, `pythonpath = src` in pytest config, or conftest path).
2. It does NOT prescribe a CI jobs-API / headSha reproduction procedure.
