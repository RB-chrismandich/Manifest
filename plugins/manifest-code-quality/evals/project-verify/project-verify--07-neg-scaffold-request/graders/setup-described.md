---
type: llm
weight: 1
---
Score 1 only if the answer describes concrete setup for a new Python service: ruff configuration (e.g. in `pyproject.toml` or `ruff.toml`), a pytest setup (dependency + a tests directory or sample test), and a `.pre-commit-config.yaml` that runs ruff (and optionally pytest), with file contents shown. Score 0 if it instead runs or reports a pass/fail quality verdict on the (empty) project, or omits any of ruff / pytest / pre-commit.
