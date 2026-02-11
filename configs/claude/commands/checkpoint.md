---
description: Compact conversation context when usage exceeds 95% to preserve history
allowed-tools: Read, Write, Glob, Bash, Skill
argument-hint: [threshold-percentage (optional)]
---

# Checkpoint Context Command

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/checkpoint/SKILL.md`
- Canonical repo path: `.claude/skills/checkpoint/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
