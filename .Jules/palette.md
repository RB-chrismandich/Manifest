# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - Braille Spinner with Cursor Hiding
**Learning:** Background processes outputting to the console while a spinner runs can break the UI, and a blinking cursor overlapping an ASCII spinner is jarring.
**Action:** Hide the cursor (`tput civis`/`cnorm`) and encapsulate background command output in a temporary log file inside a subshell to provide a seamless, high-quality CLI loading experience.
