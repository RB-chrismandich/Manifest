# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-11 - Bootstrap Spinner UX

**Learning:** The bootstrap script lacked proper cursor hiding and smooth braille
animation during long-running tasks, causing visual distraction when the cursor
jumped around the terminal. Simple ASCII spinners without cursor management feel
unpolished compared to the rest of the orchestration framework.
**Action:** Replaced the basic ASCII spinner in `bootstrap/lib/common.sh` with a
smooth braille spinner that properly hides the cursor (`tput civis`) and
restores it (`tput cnorm`). Ensured robust cleanup by isolating the spinner in a
subshell with strict `INT` and `TERM` traps to prevent the cursor from remaining
permanently hidden if the user aborts the script.
