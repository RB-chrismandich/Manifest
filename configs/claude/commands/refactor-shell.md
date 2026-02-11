---
description: Analyze Bash/Shell scripts for security, quality, and best practices
allowed-tools: Read, Glob, Grep, Bash, Skill
argument-hint: [script-path]
---

# Shell Script Refactor Analysis

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/refactor-shell/SKILL.md`
- Canonical repo path: `.claude/skills/refactor-shell/SKILL.md`

## Execution

1. Load and follow the skill file exactly.
2. Apply `$ARGUMENTS` as the command input for that skill.
3. Preserve the skill-defined safety checks, validation rules, and output format.
4. If the skill file is missing, stop and report the missing path.
