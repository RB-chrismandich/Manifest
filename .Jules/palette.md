# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-06 - CLI Spinner Output Management

**Learning:** Background processes emitting output during a loading spinner can
corrupt the terminal interface and cause visual jank.
**Action:** Always redirect background task output to a temporary file, hide
the cursor during execution, and only print the logs if the command fails to
maintain a clean UI.
