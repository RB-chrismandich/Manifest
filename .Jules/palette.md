# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - Subshell Isolation for CLI Spinners

**Learning:** Visual CLI enhancements (spinners, cursor hiding) without strict
signal trapping and process isolation cause severe accessibility and UX issues
(lost cursor, mangled stdout/stderr on exit).
**Action:** Always wrap visual background tasks in a subshell, use
`tput civis`/`cnorm` safely, and cleanly handle cleanup on `EXIT`, `INT`, and
`TERM`.
