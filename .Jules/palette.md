# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2025-04-25 - Clearing Transient CLI Displays
**Learning:** Terminal-based user interfaces (TUIs) and loading spinners can leave significant visual clutter in scrollback logs if not cleaned up after completion. This degrades the overall CLI experience and readability of the final output.
**Action:** Always instantiate `rich` library displays (like `Progress` spinners or `Live` displays) with `transient=True` to automatically remove them from the terminal once the process completes, ensuring a cleaner output log.
