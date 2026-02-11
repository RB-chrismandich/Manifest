---
description: Verify CLI tools, auth, config syntax, MCP connectivity, and symlink integrity
allowed-tools: Bash, Read, Glob, Grep
argument-hint: [category (optional)]
---

# Health Check Command

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/health-check/SKILL.md`
- Canonical repo path: `.claude/skills/health-check/SKILL.md`

## Execution

Read the skill file and follow its instructions. If `$ARGUMENTS` specifies a
category (e.g., "symlinks", "auth", "config"), run only that category's checks.
Otherwise run all checks.
