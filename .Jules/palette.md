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

## 2026-10-24 - CLI Loading Spinner UX
**Learning:** Terminal loading spinners can create a jarring experience if output is randomly emitted during animation, and especially if the cursor jumps back and forth continuously.
**Action:** Always implement shell spinners in a subshell, hide the cursor during animation (`tput civis`), buffer all output to a temporary file, restore the cursor via an `EXIT` trap (`tput cnorm`), and only print the buffered logs if the background task fails.
