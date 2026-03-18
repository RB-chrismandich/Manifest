# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - CLI Spinner UX
**Learning:** Always isolate CLI visual enhancements (spinners, cursor hiding via `tput civis`) in subshells with rigorous `EXIT`, `INT`, and `TERM` signal trapping, returning exit code 130 on interrupt. Simple exit codes fail to clean up stdout and can cause persistent cursor absence if untrapped. Native bash arrays with literal Braille unicode strings handle multi-byte characters reliably.
**Action:** Avoid implementing naive `while` spinners in the main shell context without strict `tput cnorm` cleanup and temporary file direction.
