# Palette's Journal

## 2026-02-06 - Initial Setup

**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing)
and explicit user guidance (defaults, help text).

## 2026-03-29 - CLI Usage Examples and Argument Grouping

**Learning:** For CLIs with many arguments, a flat list becomes unreadable.
Combining logical argument groups (`add_argument_group`) with a robust epilog
containing concrete usage examples (`RawDescriptionHelpFormatter`) drastically
improves CLI discoverability without adding extra dependencies.
**Action:** When working with argparse, organize options into semantic groups
and always provide executable examples in the help text.
