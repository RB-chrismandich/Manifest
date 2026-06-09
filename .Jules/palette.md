# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-09 - Transient UI Components
**Learning:** Terminal tools that use loading spinners or live displays can leave residual clutter in the user's terminal scrollback, affecting readability and causing noise for screen readers.
**Action:** When using the `rich` library (e.g., `Progress` or `Live`), instantiate them with `transient=True` so they are automatically cleared from the terminal once the process completes.
