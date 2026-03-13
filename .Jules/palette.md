# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-03-13 - Isolated CLI Visual Enhancements with Subshells and Traps
**Learning:** Visual CLI enhancements (like hiding the cursor with `tput civis` or animating spinners) require strict isolation to avoid leaving the user's terminal in a broken state on error or interruption. A simple command return or `wait` isn't enough, as `SIGINT`/`SIGTERM` will bypass standard cleanup, resulting in a permanently hidden cursor or dangling background processes.
**Action:** Always isolate CLI visual enhancements in subshells (`(...)`) with rigorous `EXIT`, `INT`, and `TERM` signal trapping. For interactive scripts with spinners, redirect background command output to a secure temporary file, kill the child PID explicitly during interrupts, restore the cursor via `tput cnorm`, and only exit with `130` on interrupt.
