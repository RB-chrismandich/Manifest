# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-11 - Transient CLI Spinners
**Learning:** Persistent loading spinners and live displays clutter terminal scrollback history after a script completes, degrading the CLI UX.
**Action:** Always use `transient=True` when instantiating `rich.progress.Progress` or `rich.live.Live` contexts to ensure UI elements cleanly vanish upon completion.
