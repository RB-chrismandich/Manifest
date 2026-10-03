---
type: llm
weight: 0.5
---
Score 1 if the answer still performs a manual code-quality pass despite not being able to execute tools — e.g. it notices the unused `json` import in `billing/invoice.py`, or the use of `datetime.datetime.utcnow()` (deprecated in favor of timezone-aware `datetime.now(datetime.UTC)`), or the missing type hints on `build_invoice`. Score 0 only if the answer gives no substantive findings at all and just states that checks are unavailable with nothing else.
