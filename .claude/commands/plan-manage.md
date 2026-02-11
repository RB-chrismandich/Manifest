---
description: Plan lifecycle with parallel agent orchestration for create/review/execute
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Task, Skill
argument-hint: [list|create|review|execute|archive|abandon] [description, filename, or issue-number]
---

# Plan Management

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/plan-manage/SKILL.md`
- Canonical repo path: `.claude/skills/plan-manage/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
