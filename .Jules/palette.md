# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2025-02-12 - Transient CLI Displays
**Learning:** In CLI applications that use rich, completed spinners or progress
bars can clutter the scrollback if left on screen.
**Action:** When instantiating rich `Progress` or `Live` components for
temporary tasks, always use `transient=True` to automatically remove them from
the terminal upon completion, keeping the output clean and accessible.
