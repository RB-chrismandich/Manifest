# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - CLI Spinner Output Management
**Learning:** When using spinners in CLI scripts, command output must be captured/redirected to prevent it from interfering with the animation.
**Action:** Always redirect stdout/stderr to a temporary file when running a command with a spinner, and only display it on failure or if explicitly requested.
