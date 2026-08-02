---
name: help
description: Search the generated offline catalog of all Manifest domain commands by name, category, or description without scanning sibling installed plugins.
---

# Command Discovery

Run `scripts/command_catalog.py` with an optional query, `--category`, `--all`,
`--limit`, or `--json`. The command reads only the adjacent generated
`catalog/commands.json`, built from all nine portable contracts and skill
frontmatter at release time.

Results use qualified names. Empty or unmatched searches are reported
deterministically; the skill never invents a substitute, invokes a command,
installs anything, or scans another plugin at runtime.
