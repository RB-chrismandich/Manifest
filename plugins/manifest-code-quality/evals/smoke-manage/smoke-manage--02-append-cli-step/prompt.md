---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(find:*)"]
runs: 3
model: sonnet
---
We don't have any smoke coverage for the CLI export command yet. Add a `Lite`-tier smoke test called `export-csv` for the `reports` app that runs the command `["reports-cli", "export", "--format", "csv"]` and expects it to exit 0.
