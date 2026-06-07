# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-06-07 - CLI Progress Indicators
**Learning:** Terminal progress spinners and live displays that are left behind clutter the user's scrollback history, making it difficult to read actual command output.
**Action:** Always instantiate `rich` library `Progress` and `Live` context managers with `transient=True` to automatically clear them when finished.
