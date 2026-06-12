## 2025-06-10 - ai-hooks-integration
**Learning:** `merge_hooks.py` completely dropped the `--command` parameter for `opencode` tools, meaning OpenCode plugins were generated without any actual hooked logic. This occurred because OpenCode generated a template string instead of parsing JSON, bypassing the core command injection logic.
**Action:** Always verify that CLI parameters are not conditionally bypassed for newer or alternative runtime tools. For templates targeting Node/JS runtimes, ensure we inject the command dynamically via format strings and execute it gracefully with robust `try/catch` wrappers.

## 2026-06-07 - issue-triage
**Learning:** Python scripts often format output as shell variable assignments intended to be sourced. Executing this output dynamically via `eval` introduces command injection risks in bash scripts if the python code or input files are altered.
**Action:** Configure automated checks to flag `eval "$(..."` or `eval \`...\`` patterns, especially those consuming output from other commands. Use a `while IFS=` loop combined with a `case` whitelist to securely parse key-value configuration directly into the shell environment without dynamic evaluation.
