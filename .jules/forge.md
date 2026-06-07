## 2026-06-07 - issue-triage
**Learning:** Python scripts often format output as shell variable assignments intended to be sourced. Executing this output dynamically via `eval` introduces command injection risks in bash scripts if the python code or input files are altered.
**Action:** Configure automated checks to flag `eval "$(..."` or `eval \`...\`` patterns, especially those consuming output from other commands. Use a `while IFS=` loop combined with a `case` whitelist to securely parse key-value configuration directly into the shell environment without dynamic evaluation.
