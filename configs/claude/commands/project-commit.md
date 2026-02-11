---
description: Generate docs, pull latest, run pre-commits, commit, and push all project changes
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, Skill, Task, AskUserQuestion
argument-hint: [commit-message (optional)]
---

# Project Commit Pipeline

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/project-commit/SKILL.md`
- Canonical repo path: `.claude/skills/project-commit/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
