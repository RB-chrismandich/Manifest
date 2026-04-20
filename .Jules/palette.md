# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2025-04-20 - CLI Progress Indicator Output

**Learning:** Progress indicators (spinners) in CLI tools are broken when the
underlying command writes to stdout or stderr, garbling the terminal display
and causing poor UX.
**Action:** When implementing CLI spinners, always redirect the command's
output to a temporary file, hide the cursor during execution, and only display
the output if the command fails.
