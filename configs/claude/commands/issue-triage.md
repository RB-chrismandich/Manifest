---
description: Comprehensive Linear issue triage with duplicate detection and priority validation
allowed-tools: [Read, Glob, Grep, Bash, Task, AskUserQuestion]
argument-hint: [--dry-run] [--close-stale] [--team TEAM]
---

# Linear Issue Triage

Automated Linear issue backlog management with duplicate detection, staleness analysis, and priority validation.

## Overview

This command performs comprehensive issue triage by:

- Detecting duplicate issues using semantic similarity
- Identifying stale/obsolete issues (deleted file references, long inactivity)
- Validating priority alignment with impact/urgency
- Using parallel agents for complex/ambiguous decisions
- Generating actionable recommendations with confidence scores

## Execution Strategy

Use the shared skill workflow as the source of truth.

- **Skill path**: `~/.claude/skills/issue-triage/SKILL.md`
- **Canonical repo path**: `.claude/skills/issue-triage/SKILL.md`

## Implementation

1. Load and follow the skill file exactly
2. Apply `$ARGUMENTS` as the command input for that skill
3. Preserve the skill-defined safety checks, validation rules, and output format
4. If the skill file is missing, stop and report the missing path

## Safety Rules

- Never auto-close issues with "planned" label
- Require ≥85% consensus for duplicate marking
- Verify file deletion before marking stale
- Require explicit `--close-stale` flag for cancellations
- Log all actions to audit trail

## Arguments

```bash
/issue-triage [--dry-run] [--close-stale] [--team TEAM] [--priority N] [--limit N]
```

| Argument | Description |
|----------|-------------|
| `--dry-run` | Analysis only, no mutations (default: false) |
| `--close-stale` | Auto-cancel stale issues (requires explicit flag) |
| `--team TEAM` | Filter by team key (e.g., "ENG", "PRODUCT") |
| `--priority N` | Filter by priority (0-4) |
| `--limit N` | Max issues to analyze (default: 500) |

## Example Usage

```bash
# Dry-run analysis of all issues
/issue-triage --dry-run

# Analyze specific team
/issue-triage --dry-run --team ENG

# Live run: mark duplicates only
/issue-triage

# Live run: mark duplicates AND close stale
/issue-triage --close-stale

# Analyze high-priority issues only
/issue-triage --priority 1 --dry-run
```
