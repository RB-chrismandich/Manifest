# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-02-12 - Improve argparse CLI UX

**Learning:** Argument grouping (`add_argument_group`) and providing concrete usage
examples via an `epilog` with `argparse.RawDescriptionHelpFormatter` significantly
improves the usability of `argparse`-based CLI tools with many options.
**Action:** When designing or refactoring CLI interfaces in Python, group arguments
logically and provide realistic examples in the help text to reduce cognitive load
on the user.
