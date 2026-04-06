# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-06 - CLI Help Menu Formatting

**Learning:** Python CLI tools with many options (like `parallel_agent.py`) can
easily become overwhelming for users when arguments are presented in a flat
list.
**Action:** Use `argparse.add_argument_group()` to logically categorize options,
and `argparse.RawDescriptionHelpFormatter` with an `epilog` to provide concrete
usage examples, significantly improving the developer experience.
