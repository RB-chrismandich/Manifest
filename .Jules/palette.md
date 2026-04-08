# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-12 - CLI Help Output Usability

**Learning:** For `argparse`-based Python CLI tools with many options,
presenting a flat list of arguments makes the tool hard to use.
**Action:** Use `add_argument_group()` to logically group related flags
(e.g., Execution Modes, Agent Toggles) and use
`argparse.RawDescriptionHelpFormatter` with an `epilog` to provide concrete
copy-pasteable usage examples directly in `--help`.
