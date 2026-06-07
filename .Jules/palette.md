# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2024-06-07 - Transient UI Components
**Learning:** Persistent CLI loading spinners or live displays can
leave a trail of cluttered state after completion, frustrating users
tracking progress.
**Action:** Add `transient=True` to `rich` Progress and Live components
so they smoothly clear themselves upon completion.
