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

- **Linear MCP** available in the active harness OR
- **Linear API key** supplied through the `LINEAR_API_KEY` environment variable
- **Tools**: `jq`, `python3`

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dry-run` | Analysis only, no mutations | false |
| `--close-stale` | Auto-cancel stale issues | false (requires explicit flag) |
| `--team TEAM` | Filter by team key | all teams |
| `--priority N` | Filter by priority (0-4) | all priorities |
| `--limit N` | Max issues to analyze | 500 |

## Safety Rules

1. **Never auto-close issues with "planned" label**
2. **Require ≥85% consensus for duplicate marking**
3. **Verify file deletion before marking stale**
4. **Require explicit --close-stale flag**
5. **Log all actions to audit trail**

## Output

- **Markdown report** with recommendations
- **JSON audit log** in `$XDG_STATE_HOME/manifest/forge/triage_audits/`
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

Create `$XDG_CONFIG_HOME/manifest/forge/tracker_triage.json` to override defaults
without modifying the immutable bundle:

- Duplicate detection thresholds
- Staleness criteria (inactivity days, file deletion ratio)
- Priority scoring formula weights
- Consensus thresholds
- Action safety rules

## Troubleshooting

### Linear authentication required

- Configure native Linear MCP auth or export `LINEAR_API_KEY` for the CLI runtime

### jq command not found

- Install: `brew install jq` (macOS) or `apt-get install jq` (Linux)

### No issues found

- Check team filter (`--team`) and priority filter (`--priority`)
- Verify Linear API access

### Permission denied: ../../runtime/bin/linear_ops.sh

- Make executable: `chmod +x ../../runtime/bin/linear_ops.sh`

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Main skill implementation |
| `../../runtime/bin/linear_ops.sh` | Linear MCP wrapper |
| `../../runtime/config/tracker_triage.json` | Configuration (provider-neutral) |

## See Also

- [Linear API Documentation](https://developers.linear.app/docs)
- `manifest-workspace:parallel-agent` for optional consensus checks
- The active harness's native plan-management documentation
