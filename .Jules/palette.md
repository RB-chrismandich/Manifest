# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-03-14 - Robust CLI Spinners

**Learning:** Simple ASCII spinners easily break formatting if the background
process writes to stdout/stderr or if the user interrupts the script
(leaving the cursor hidden).
**Action:** Always isolate CLI enhancements like spinners in subshells.
Hide the cursor (`tput civis`) but rigorously trap `EXIT`, `INT`, and
`TERM` signals to restore it (`tput cnorm`), kill child processes, and
cleanup temporary logs. Redirect background output to a temp file and
only display it on failure.
