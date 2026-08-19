---
name: shell-audit
description: Unified shell script safety and control-flow auditor. Runs both pipefail command substitution and errexit control-flow audits across target scripts in one pass.
---

# Unified Shell Safety & Control-Flow Audit

Orchestrate both shell audit sub-engines (`shell-audit-pipefail` and `shell-audit-errexit`)
across shell scripts in a target repository or path.

## When to use

- Auditing shell scripts for silent abortion, unsafe command substitutions, and unintended `errexit` control-flow triggers.
- Pre-commit verification for complex bash/shell pipelines.

## Sub-Engine Dispatch

1. **Pipefail & Command Substitutions**:
   - Dispatches `/manifest-code-quality:shell-audit-pipefail <target>`.
   - Checks `set -euo pipefail` scripts for `$()` command substitutions that silently exit on empty or malformed output.

2. **Control-Flow & Errexit Triggers**:
   - Dispatches `/manifest-code-quality:shell-audit-errexit <target>`.
   - Audits non-subshell control structures (`if`, `while`, arithmetic `(( ))`,
     pipelines) for unexpected zero/non-zero exits under `set -e`.

## Workflow

1. Identify all target scripts (`.sh`, `.bash`, `.zsh`, executable shell files).
2. Run both sub-engines concurrently.
3. Consolidate findings into a single prioritized report:
   - **Critical**: Unhandled command substitutions that crash scripts under `-e`.
   - **High**: Control flow statements susceptible to silent early exit.
   - **Advisory**: Missing defensive fallback patterns (e.g. `|| true` or default expansions).
