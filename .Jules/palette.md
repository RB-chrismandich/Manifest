# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - Resilient CLI Spinners

**Learning:** Visual polish like hiding the cursor during async CLI operations
(`tput civis`) can severely impact UX if not safely trapped. Failing to restore
the cursor or clean up background PIDs on `SIGINT`/`SIGTERM` results in a broken
terminal state for the user.
**Action:** Always encapsulate terminal visual modifications in a subshell,
rigorously trapping signals (`EXIT`, `INT`, `TERM`) to guarantee state
restoration (`tput cnorm`) and proper child process termination, regardless of
how the script exits.
