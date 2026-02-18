# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - [CLI Spinner Pattern]
**Learning:** Animated spinners in shell scripts must degrade gracefully (no animation) in non-interactive environments (`! -t 1`, `TERM=dumb`).
**Action:** When implementing CLI progress indicators, always check for TTY capabilities and capture stdout/stderr to a temp file to reduce noise on success but preserve debugging context on failure.
