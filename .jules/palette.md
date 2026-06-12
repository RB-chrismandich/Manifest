# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-06-08 - Rich Terminal UI Persistence
**Learning:** By default, rich `Progress` and `Live` instances leave their
final output in the terminal scrollback, causing unnecessary clutter during
repeated script executions.
**Action:** Instantiate these UI components with `transient=True` to
automatically clear them upon completion, keeping the user's terminal history
clean.

## 2026-06-10 - CLI Spinner Terminal UX
**Learning:** In bash scripts, hiding the cursor for a cleaner spinner requires careful lifecycle management. Relying solely on an `EXIT` trap is insufficient, as `SIGINT` (Ctrl+C) bypasses it, leaving the user with a broken (invisible) cursor. Output buffering is also crucial to prevent standard output from clobbering the spinner line.
**Action:** Always buffer output to a temp file, print it only on error, and trap `INT`, `TERM`, and `EXIT` to ensure `tput cnorm` restores the terminal cursor regardless of how the script terminates.
