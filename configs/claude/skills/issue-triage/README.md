# Issue Triage Skill

Comprehensive Linear issue audit with duplicate detection, staleness analysis, and priority validation.

## Quick Start

```bash
# Dry-run analysis (safe, no mutations)
/issue-triage --dry-run

# Live run (marks duplicates only)
/issue-triage

# Full cleanup (marks duplicates AND closes stale)
/issue-triage --close-stale
```

## What It Does

1. **Duplicate Detection**
   - Fuzzy title matching (≥80% = HIGH, 70-85% = MEDIUM)
   - Description overlap analysis
   - Parallel agent verification for gray areas
   - Auto-marks HIGH confidence duplicates (≥85% consensus)

2. **Staleness Detection**
   - Identifies inactive issues (90+ days, no priority, no labels)
   - Detects deleted file references (>50% files missing)
   - **Respects "planned" label** - never auto-closes
   - Requires explicit `--close-stale` flag

3. **Priority Validation**
   - Scores issues on Impact/Urgency/Readiness/Risk (1-5 each)
   - Formula: (Impact × 3) + (Urgency × 2) + (Readiness × 2) - Risk
   - Maps scores to Linear priorities (0-4)
   - Flags misalignments for manual review

## Prerequisites

- **Linear MCP** configured in `~/.claude/config/mcp_servers.yml` OR
- **Linear API key** in `~/.config/linear/token`
- **Tools**: `jq`, `python3`

## Arguments

| Argument        | Description                 | Default                        |
| --------------- | --------------------------- | ------------------------------ |
| `--dry-run`     | Analysis only, no mutations | false                          |
| `--close-stale` | Auto-cancel stale issues    | false (requires explicit flag) |
| `--team TEAM`   | Filter by team key          | all teams                      |
| `--priority N`  | Filter by priority (0-4)    | all priorities                 |
| `--limit N`     | Max issues to analyze       | 500                            |

## Safety Rules

1. **Never auto-close issues with "planned" label**
2. **Require ≥85% consensus for duplicate marking**
3. **Verify file deletion before marking stale**
4. **Require explicit --close-stale flag**
5. **Log all actions to audit trail**

## Output

- **Markdown report** with recommendations
- **JSON audit log** in `~/.claude/.agent_outputs/triage_audits/`
- **Action summary** with counts

## Example Workflows

### Weekly Backlog Cleanup

```bash
# 1. Dry-run to preview
/issue-triage --dry-run --team ENG

# 2. Review recommendations
# 3. Execute safe actions (duplicates)
/issue-triage --team ENG

# 4. Manually review stale issues
# 5. Close stale if approved
/issue-triage --team ENG --close-stale
```

### Priority Audit

```bash
# Check all high-priority issues
/issue-triage --priority 1 --dry-run

# Check unassigned issues
/issue-triage --priority 0 --dry-run
```

### Full Triage (All Teams)

```bash
# Analyze entire backlog
/issue-triage --dry-run --limit 1000

# Execute after review
/issue-triage --close-stale
```

## Parallel Agent Integration

Parallel agents invoked for:

- **Medium-confidence duplicates** (70-85% similarity)
- **Priority scoring** (complex impact assessment)
- **Gray-area staleness** (conflicting signals)

Consensus thresholds:

- ≥85%: AUTO-EXECUTE
- 70-84%: RECOMMEND
- 50-69%: HIGHLIGHT disagreements
- <50%: ESCALATE to user

## Configuration

Edit `~/.claude/config/linear_triage.yml` to customize:

- Duplicate detection thresholds
- Staleness criteria (inactivity days, file deletion ratio)
- Priority scoring formula weights
- Consensus thresholds
- Action safety rules

## Troubleshooting

### Linear authentication required

- Configure Linear MCP OR set API key in `~/.config/linear/token`

### jq command not found

- Install: `brew install jq` (macOS) or `apt-get install jq` (Linux)

### No issues found

- Check team filter (`--team`) and priority filter (`--priority`)
- Verify Linear API access

### Permission denied: ~/.claude/scripts/linear_ops.sh

- Make executable: `chmod +x ~/.claude/scripts/linear_ops.sh`

## Files

| File                                    | Purpose                      |
| --------------------------------------- | ---------------------------- |
| `SKILL.md`                              | Main skill implementation    |
| `~/.claude/scripts/linear_ops.sh`       | Linear MCP wrapper           |
| `~/.claude/config/linear_triage.yml`    | Configuration                |
| `~/.claude/prompts/triage_synthesis.md` | Agent disagreement synthesis |
| `~/.claude/commands/issue-triage.md`    | Claude command wrapper       |
| `.gemini/commands/issue-triage.toml`    | Gemini command wrapper       |

## See Also

- [Linear API Documentation](https://developers.linear.app/docs)
- [Parallel Agent Guide](~/.claude/CLAUDE.md)
- [Plan Management](~/.claude/.plans/README.md)
