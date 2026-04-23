# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-11 - Polish CLI Loaders

**Learning:** Missing loading states, noisy stdout from background tasks, and
flashy cursors create janky CLI experiences.
**Action:** Implement braille spinners in subshells, capture logs in temp files
(only printing on failure), and gracefully manage the terminal cursor
(`tput civis/cnorm`) via `EXIT` traps to ensure clean output.
