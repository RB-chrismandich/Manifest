# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-11 - Robust CLI visual enhancements

**Learning:** Visual enhancements in CLI scripts (like hiding the cursor with
`tput civis` and showing spinners) must be strictly isolated. Failure to clean
up standard output properly on failures or user interruptions causes lasting
terminal state corruption (invisible cursor).
**Action:** When building custom CLI interactions in bash, always execute them
in a subshell `(...)` and implement rigorous `EXIT`, `INT`, and `TERM` traps to
guarantee state cleanup (e.g. `tput cnorm`) regardless of the script's exit
state.
