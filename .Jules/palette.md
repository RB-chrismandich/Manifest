# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-11 - Grouping CLI Arguments
**Learning:** Dense CLI tools with many options can be overwhelming and hard to scan for users.
**Action:** Use `add_argument_group()` to logically group arguments, and provide concrete examples using `argparse.RawDescriptionHelpFormatter` to improve readability and discoverability.
