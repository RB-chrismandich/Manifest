# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-03-08 - Better CLI Feedback Using Braille Spinners
**Learning:** Using a simple ASCII spinner often results in choppy visuals and messy terminal logs when background tasks write output unexpectedly.
**Action:** When creating CLI spinners, use a rich Braille array `("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")` and redirect command output to a secure temp log (`mktemp`). By executing the spinner and task in a subshell with properly trapped signals, output can be hidden during success and only printed on failure, resulting in a significantly cleaner user experience.
