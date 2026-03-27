# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-11 - CLI Spinner Cursor Visibility

**Learning:** Flashing CLI cursors during a running visual element like a
spinner causes distracting blinking artifacts that degrade user experience.
**Action:** Always wrap visual CLI enhancements in subshells, hide the cursor
with `tput civis`, and strictly trap signals (`EXIT`, `INT`, `TERM`) to
restore the cursor using `tput cnorm`.
