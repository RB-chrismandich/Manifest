# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2025-02-12 - CLI Spinner UX and Safety

**Learning:** Simple CLI visual enhancements (like spinners and cursor hiding
via `tput civis`) can create permanent UX regressions (e.g., hidden cursors)
if the script exits abruptly without rigorous signal handling.
**Action:** Always isolate CLI visual enhancements in subshells with rigorous
`EXIT`, `INT`, and `TERM` signal trapping to securely clean up temporary files
and restore the cursor state, returning standard interrupt codes on failure.
