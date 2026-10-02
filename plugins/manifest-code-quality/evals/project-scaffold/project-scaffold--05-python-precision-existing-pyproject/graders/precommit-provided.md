---
type: llm
focus: last_message
weight: 1
---
The eval harness blocks writing dotfiles, so `.pre-commit-config.yaml` may not be writable in this run. The skill's Python template uses the hooks `ruff`, `ruff-format`, `mypy` and `gitleaks` (no pytest hook). Score 1 only if the answer EITHER created `.pre-commit-config.yaml`, OR shows its intended contents — including at least a `ruff` hook (the template's `ruff-format`/`mypy`/`gitleaks` hooks are expected; a pytest hook is optional, neither required nor penalized) — and clearly states it could not be written. Score 0 if the pre-commit config is silently omitted, or the answer claims it was created when the write was blocked.
