# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-03-12 - Spinner Subshell Isolation
**Learning:** Background process spinlock polling and cursor manipulations (like `tput civis`) in CLI interfaces can easily leak and cause persistent cursor absence if not properly trapped via subshells. Simple exit codes also don't clean up stdout.
**Action:** Always isolate CLI visual enhancements (spinners, cursor hiding) in their own subshells with rigorous signal trapping, returning `130` on interrupt instead of normal failure.
