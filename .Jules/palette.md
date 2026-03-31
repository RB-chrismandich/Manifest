# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-03-31 - Improve Python CLI UX via Argparse Grouping

**Learning:** Organizing CLI arguments into logical groups using
`argparse.add_argument_group` drastically improves readability and discoverability
when a tool scales to 20+ arguments.
**Action:** Default to grouping arguments by function (e.g., Output, Models,
Control) and adding an `epilog` with concrete usage examples for all complex
Python CLI utilities.
