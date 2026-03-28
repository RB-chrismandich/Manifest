# Palette's Journal

## 2026-02-12 - CLI Argument Grouping UX

**Learning:** For scripts with many CLI arguments (like parallel_agent.py),
throwing all arguments into a single list makes it overwhelming for the user to
find what they need. Logical grouping and providing usage examples significantly
improves discoverability.
**Action:** Use `add_argument_group()` in argparse for scripts with numerous
options and supply an epilog with `argparse.RawDescriptionHelpFormatter` to
display concrete examples.

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors,
spacing) and explicit user guidance (defaults, help text).
