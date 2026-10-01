---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Edit, Read, Grep, Glob, "Bash(mkdir:*)", "Bash(ln:*)"]
runs: 3
model: sonnet
---
Scaffold a new Terraform project named `network-baseline` in this empty directory — tflint config and the standard variable/output files.
