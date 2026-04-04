# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).

## 2026-02-12 - Grouping CLI Arguments

**Learning:** CLIs with many arguments become overwhelming; unstructured help
menus degrade UX.
**Action:** Use `add_argument_group` in argparse to organize options logically,
and provide concrete usage examples via `epilog` to make complex commands
instantly understandable.
