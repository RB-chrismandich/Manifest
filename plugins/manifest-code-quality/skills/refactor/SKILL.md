---
name: refactor
description: Inspect a target file or codebase, detect language, and route to the matching refactoring engine.
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

Use the [review escalation contract](references/review-escalation.md). Route a
target to its language engine with one capable reviewer by default. Escalate
only when at least one of that contract's five risk conditions is present;
this overrides any count or size threshold. A target covering Python, Go, and
Shell remains single-agent unless it presents one of those conditions.

## Sub-agent dispatch

When escalation is warranted, dispatch independent reviewers only for genuinely
independent analysis tracks, then synthesize their findings. Otherwise analyze
inline. Dispatched reviewers do not re-dispatch.
