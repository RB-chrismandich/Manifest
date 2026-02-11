---
description: Capture and query structured lessons learned in the knowledge base
allowed-tools: Read, Glob, Grep, Bash, Skill
argument-hint: [file-or-directory]
---

# Learning Loop

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/learning-loop/SKILL.md`
- Canonical repo path: `.claude/skills/learning-loop/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
