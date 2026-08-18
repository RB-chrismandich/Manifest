---
name: refactor
description: Inspect a target file or codebase, detect language, and route to the matching refactoring engine (Python, Go, Node/TypeScript, Shell, Terraform) with parallel agent verification.
---

# Unified Codebase Refactor Dispatcher

Inspect target files or directory, detect language, and route execution to the
matching language-specific refactoring engine.

## When to use

- You want to refactor code without remembering the exact language-specific command.
- You have a multi-language repository or mixed-file changes.
- Refactoring a single file whose extension dictates the analyzer.

## Routing Rules

Inspect the target path and dispatch to the matching specialized engine:

| Target Pattern / Ecosystem | Specialized Engine |
|-----------------------------|--------------------|
| `.py`, `pyproject.toml`, `requirements.txt` | `/manifest-code-quality:python-refactor` |
| `.go`, `go.mod` | `/manifest-code-quality:go-refactor` |
| `.ts`, `.tsx`, `.js`, `.jsx`, `package.json` | `/manifest-code-quality:node-refactor` |
| `.sh`, `.bash`, `.zsh` | `/manifest-code-quality:shell-refactor` |
| `.tf`, `.hcl`, `versions.tf` | `/manifest-code-quality:terraform-refactor` |

## Workflow

1. **Target Identification**:
   - If a specific file is provided, check its extension and dispatch immediately to the matching engine.
   - If a directory is provided, scan for dominant languages and configuration
     markers (`go.mod`, `package.json`, `pyproject.toml`, etc.).

2. **Single-Language Target**:
   - Delegate directly to the matching engine (e.g. `/manifest-code-quality:python-refactor <target>`).
   - Inherit the engine's 4-phase analysis and parallel agent cross-verification.

3. **Multi-Language Target**:
   - Dispatch sub-agents for each detected language domain.
   - Aggregate findings into a prioritized, cross-stack refactoring roadmap ordered by risk and architectural impact.
