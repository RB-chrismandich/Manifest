# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-12 - Smooth CLI Loading States

**Learning:** Background processes that use spinners without hiding the cursor
cause visual jitter for users. Standard stdout updates cause the cursor block to
rapidly flick across characters.
**Action:** Always wrap background loaders in subshells that use `tput civis` to
hide the cursor, and ensure an `EXIT` trap triggers `tput cnorm` to restore
terminal state reliably even on failure.
