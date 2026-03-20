# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-11 - CLI Spinner Polishing
**Learning:** Legacy ASCII spinners (`-\|/`) and unmanaged cursors create a jittery, unpolished CLI experience, particularly during long-running tasks.
**Action:** Always encapsulate CLI visual enhancements (like Braille spinners) in subshells with rigorous signal trapping (`EXIT`, `INT`, `TERM`) to hide the cursor securely (`tput civis`) and ensure cleanup, preventing persistent missing cursors or orphaned background processes.
