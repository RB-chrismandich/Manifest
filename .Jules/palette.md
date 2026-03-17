# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-06 - CLI Spinner UX

**Learning:** Command-line visual enhancements (like hiding the cursor or custom
spinners) can persist if not properly sandboxed and cleaned up on unexpected
exits, leading to a frustrating user experience (e.g., a missing terminal
cursor).
**Action:** Always isolate visual CLI enhancements in a subshell, use `mktemp`
for safe logging, and enforce rigid signal trapping (`INT`, `TERM`, `EXIT`) to
restore standard state (like `tput cnorm`) regardless of how the command fails.
