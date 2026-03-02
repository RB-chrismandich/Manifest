# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-03-02 - CLI Loading Spinners
**Learning:** Simple CLI spin animations can easily clutter the terminal if errors are emitted dynamically or if the process exits leaving visual artifacts.
**Action:** Use standard Braille spinners, hide the cursor during operation (`tput civis`), handle output redirection, and clearly mark exit states with colorized icons to ensure a clean UI flow for scripts.
