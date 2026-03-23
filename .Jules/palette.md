# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2025-03-23 - Subshell Execution & Traps for CLI Visuals
**Learning:** Simple background processes for CLI visual enhancements (like spinners) can leave terminal cursors hidden or output garbled if interrupted (Ctrl+C). Relying on simple return codes fails to handle SIGINT/SIGTERM properly.
**Action:** Always isolate CLI visual enhancements (spinners, cursor hiding via `tput civis`) in subshells with rigorous `EXIT`, `INT`, and `TERM` signal trapping, returning exit code 130 on interrupt. Simple exit codes fail to clean up stdout and can cause persistent cursor absence if untrapped.
