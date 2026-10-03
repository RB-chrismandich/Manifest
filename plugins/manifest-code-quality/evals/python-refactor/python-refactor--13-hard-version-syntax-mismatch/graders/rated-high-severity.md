---
type: llm
weight: 1
---
Score 1 only if the version/syntax mismatch finding (PEP 604 `|` unions vs. `requires-python = ">=3.8"`) is rated at a severity consistent with breaking the module entirely on a supported Python version (e.g. High or Critical, or placed in an "Immediate"/"Quick Win" priority tier) — not filed as a low-severity style nit alongside things like naming or docstrings. Score 0 if the finding is missing, or is present but rated/prioritized as purely cosmetic (e.g. grouped only with "prefer modern syntax" style suggestions with no severity attached).
