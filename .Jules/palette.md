# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-03-01 - Silent CLI Failures from `set -e`
**Learning:** Using `set -e` with arithmetic evaluations like `((VAR++))` causes silent script termination when `VAR` starts at `0`. This results in poor UX because the user gets no error message or summary output.
**Action:** Always append `|| true` to incrementing arithmetic evaluations (e.g., `((VAR++)) || true`) in shell scripts running under `set -e` to ensure the script completes its intended UX flow, such as printing summaries.
