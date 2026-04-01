# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance
(defaults, help text).

## 2026-02-11 - CLI Usability Improvement

**Learning:** Python CLI tools with many arguments can be overwhelming to users if not structured logically.
**Action:** Use `add_argument_group()` in `argparse` to group arguments logically and use
`argparse.RawDescriptionHelpFormatter` with an `epilog` to provide concrete examples in the help text.
