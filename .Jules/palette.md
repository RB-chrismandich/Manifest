# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-11 - Robust CLI Spinners

**Learning:** Background process output easily corrupts interactive CLI loading
animations, leading to a degraded UX when users see broken terminal lines or
interleaved text.
**Action:** When implementing CLI spinners, always hide the terminal cursor
(`tput civis`), redirect command output to a temporary log file, restore the
cursor upon exit (`tput cnorm`), and only print the log contents if the command
ultimately fails.
