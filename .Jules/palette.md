# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance
(defaults, help text).

## 2026-03-05 - Argparse Grouping

**Learning:** CLIs built with `argparse` can quickly become overwhelming for users when the tool has many flags.
Monolithic lists of arguments are hard to parse visually.
**Action:** Use `add_argument_group()` to logically group related arguments (e.g., Mode, Output, Execution,
Agent Selection, Model Selection) and add an `epilog` with concrete examples via
`argparse.RawDescriptionHelpFormatter`.
