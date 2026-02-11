---
description: Configure CI/CD pipelines based on detected languages and project structure
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Skill
argument-hint: [github|gitlab] [project-path]
---

# CI Setup

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/ci-setup/SKILL.md`
- Canonical repo path: `.claude/skills/ci-setup/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
