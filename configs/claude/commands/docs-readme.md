---
description: Analyze project structure and improve README documentation following best practices
allowed-tools: Read, Glob, Grep, Skill
argument-hint: [readme-path]
---

# README Improvement Command

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/docs-readme/SKILL.md`
- Canonical repo path: `.claude/skills/docs-readme/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
