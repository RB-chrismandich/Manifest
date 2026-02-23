# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).
## 2026-02-23 - Better CLI Spinners
**Learning:** Users appreciate seeing logs when things go wrong, but hate them when things go right. Redirecting output to a tmp file and only showing it on failure is the sweet spot.
**Action:** Use 'run_with_spinner' pattern for all long-running CLI tasks.
