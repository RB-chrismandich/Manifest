# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit
user guidance (defaults, help text).

## 2026-02-11 - Isolate CLI Spinner and Cursor Restoration

**Learning:** Simple return codes fail to restore the cursor state if aborted when hiding the
cursor via `tput civis`. If a process with a spinner exits prematurely or is interrupted, the
terminal cursor remains hidden, degrading the UX for the developer.
**Action:** Always isolate CLI visual enhancements (spinners, cursor hiding) in subshells with
rigorous `EXIT`, `INT`, and `TERM` signal trapping to guarantee cleanup (restoring cursor via
`tput cnorm`, removing temp logs) and return exit code `130` on interrupt.
