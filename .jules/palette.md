# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-06-08 - Rich Terminal UI Persistence

**Learning:** By default, rich `Progress` and `Live` instances leave their
final output in the terminal scrollback, causing unnecessary clutter during
repeated script executions.
**Action:** Instantiate these UI components with `transient=True` to
automatically clear them upon completion, keeping the user's terminal history
clean.

## 2026-06-10 - CLI Spinner Terminal UX

**Learning:** In bash scripts, hiding the cursor for a cleaner spinner requires
careful lifecycle management. Relying solely on an `EXIT` trap is insufficient,
as `SIGINT` (Ctrl+C) bypasses it, leaving the user with a broken (invisible)
cursor. Output buffering is also crucial to prevent standard output from
clobbering the spinner line.
**Action:** Always buffer output to a temp file, print it only on error, and
trap `INT`, `TERM`, and `EXIT` to ensure `tput cnorm` restores the terminal
cursor regardless of how the script terminates.

## 2024-06-16 - Add rich styling to status in CLI table output

**Learning:** The CLI tool outputs the agent status ("complete" / "failed") but doesn't utilize `rich` color tags
for status text within the summary table in `orchestrator.py`, leading to poor visual contrast.
**Action:** Enhance the `table.add_row` call to include color tags for the status string.

## 2026-06-19 - Semantic Colors for CLI Validation States

**Learning:** Binary green/red schemes in CLI outputs fail to communicate
intermediate states like warnings or manual review requests, confusing users
when a process didn't fully fail but isn't fully approved.
**Action:** Use a three-color semantic system (green=success, yellow=warning/review,
red=error/blocked) for validation verdicts to provide nuanced visual feedback.

## 2026-06-27 - CLI Spinner Elapsed Time Indicator

**Learning:** When designing CLI spinners for long-running tasks, missing an elapsed time indicator can cause
users to prematurely abort the operation because they lack continuous visual feedback.
**Action:** Always include an elapsed time indicator (like `TimeElapsedColumn()`) alongside the spinner to provide
continuous visual feedback.
