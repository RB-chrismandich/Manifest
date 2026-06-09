# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-05-31 - Transient Terminal UI
**Learning:** Progress bars and live update panels in CLI tools leave behind "stale" state strings (like `Working...`) that pollute the terminal scrollback buffer and create noise for screen readers after the process has successfully completed.
**Action:** When using terminal rendering libraries like `rich` for async indicators (Progress, Live panels), always instantiate them with `transient=True` so they automatically clear themselves upon exit, leaving only the final structural output.
