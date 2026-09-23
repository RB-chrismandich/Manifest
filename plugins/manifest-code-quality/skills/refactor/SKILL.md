---
name: refactor
description: Inspect a target file or codebase, detect language, and route to the matching refactoring engine (Python, Go, Node/TypeScript, Shell, Terraform) with OMP sub-agent verification.
---

# Unified Codebase Refactor Dispatcher

Inspect target files or directory, detect language, and route execution to the
matching language-specific refactoring engine.

## Routing Rules

| Target Pattern / Ecosystem | Specialized Engine |
|-----------------------------|--------------------|
| `.py`, `pyproject.toml`, `requirements.txt` | `/manifest-code-quality:python-refactor` |
| `.go`, `go.mod` | `/manifest-code-quality:go-refactor` |
| `.ts`, `.tsx`, `.js`, `.jsx`, `package.json` | `/manifest-code-quality:node-refactor` |
| `.sh`, `.bash`, `.zsh` | `/manifest-code-quality:shell-refactor` |
| `.tf`, `.hcl`, `versions.tf` | `/manifest-code-quality:terraform-refactor` |

## Review routing

Use the [review escalation contract](references/review-escalation.md). For
every detected ecosystem, invoke every matching engine sequentially with one
capable reviewer by default, then aggregate the engine reports into one
prioritized cross-stack roadmap. Escalate to independent review only when at
least one of that contract's five risk conditions is present; counts and size
thresholds never escalate review by themselves. A target covering Python, Go,
and Shell therefore remains single-agent while still running all three engines
and aggregating their results unless a risk condition is present.

## Sub-agent dispatch

Follow the [dispatch mechanics](references/refactor-dispatch.md), the
[shared dispatch contract](../../runtime/references/sub-agent-dispatch.md), and
the [review escalation contract](references/review-escalation.md). When a risk
condition warrants escalation, obtain an independent review through the current
host's native mechanism; partition reviewers only when the investigation has
genuinely independent analysis tracks; otherwise the second review examines the
same target independently.
Submit independent review units in one native call, using the `reviewer`
specialist where available; children execute directly and never redispatch. If
sub-agent dispatch is unavailable, review inline and report `DEGRADED`.
