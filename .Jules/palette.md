# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-06 - Braille Spinner with Clean Exit

**Learning:** Background processes in CLI tools often clobber standard output
and leave artifacts (like cursors) on error.
**Action:** Implement robust subshell traps for spinners to hide/restore
cursors and pipe background task logs to temporary files, displaying them
only on failure.
