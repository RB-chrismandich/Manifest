---
name: issue-triage
description: "Comprehensive Linear issue audit: validate prioritization, identify duplicates and overlapping issues, detect stale/obsolete issues, produce clean actionable backlog"
---

# Linear Issue Triage Skill

Automated Linear issue backlog management with duplicate detection, staleness analysis, and priority validation.

## Purpose

This skill performs comprehensive issue triage by:

1. Detecting duplicate issues using semantic similarity
2. Identifying stale/obsolete issues (deleted file references, long inactivity)
3. Validating priority alignment with impact/urgency
4. Using parallel agents for complex/ambiguous decisions
5. Generating actionable recommendations with confidence scores

## Arguments

```bash
/issue-triage [--dry-run] [--close-stale] [--team TEAM] [--priority N] [--limit N]
```

| Argument | Description | Default |
|----------|-------------|---------|
| `--dry-run` | Analysis only, no mutations | false |
| `--close-stale` | Auto-cancel stale issues (requires explicit flag) | false |
| `--team TEAM` | Filter by team key (e.g., "ENG", "PRODUCT") | all teams |
| `--priority N` | Filter by priority (0-4) | all priorities |
| `--limit N` | Max issues to analyze | 500 |

## Prerequisites

1. **Linear MCP configured** in `~/.claude/config/mcp_servers.yml` OR
2. **Linear API key** in `~/.config/linear/token`
3. **Tools installed**: `jq`, `python3`
4. **Scripts available**: `~/.claude/scripts/linear_ops.sh`, `~/.claude/scripts/parallel_agent.py`
5. **Config loaded**: `~/.claude/config/linear_triage.yml`

## Workflow

The full step-by-step workflow — including the exact scripts to run at each step — lives in [references/workflow.md](references/workflow.md). **Read that file and execute each step in order in one shell session** (later steps consume env vars and intermediate files set by earlier ones). Steps:

1. Step 1: Load Configuration
2. Step 2: Fetch Issues
3. Step 3: Parse and Classify Issues
4. Step 4: Duplicate Detection
5. Step 5: Staleness Detection
6. Step 6: Priority Validation
7. Step 7: Generate Recommendations
8. Step 8: Execute Actions

## Safety Rules

1. **Never auto-close issues with "planned" label** - these are intentionally kept in backlog
2. **Require ≥85% consensus for duplicate marking** - conservative threshold to avoid false positives
3. **Verify file deletion before marking stale** - check if files truly don't exist
4. **Require explicit --close-stale flag** - no accidental closures
5. **Log all actions to audit trail** - full accountability

## Error Handling

```bash
# Wrapper for safe execution
trap 'echo "Error on line $LINENO. Exiting."; exit 1' ERR

# Validate prerequisites before starting
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed" >&2
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed" >&2
    exit 1
fi

if [[ ! -x ~/.claude/scripts/linear_ops.sh ]]; then
    echo "Error: linear_ops.sh not found or not executable" >&2
    exit 1
fi

if [[ ! -f ~/.claude/config/linear_triage.yml ]]; then
    echo "Error: Configuration file not found" >&2
    exit 1
fi
```

## Example Usage

```bash
# Dry-run analysis of all issues
/issue-triage --dry-run

# Analyze specific team
/issue-triage --dry-run --team ENG

# Live run: mark duplicates only (safe)
/issue-triage

# Live run: mark duplicates AND close stale issues (requires explicit flag)
/issue-triage --close-stale

# Analyze only high-priority issues
/issue-triage --priority 1 --dry-run
```

## Output

- **Markdown report** to console and temp file
- **JSON audit log** in `~/.claude/.agent_outputs/triage_audits/`
- **Action summary** with counts and recommendations

## Integration with Parallel Agents

Parallel agents are invoked for:

1. **Medium-confidence duplicates** (70-85% similarity) - Get semantic verification
2. **Priority scoring** - Use multi-agent consensus for impact/urgency assessment
3. **Gray-area staleness** - Issues with "planned" label but deleted files

Consensus thresholds:

- ≥85%: AUTO-EXECUTE (duplicates only)
- 70-84%: RECOMMEND (require user approval)
- 50-69%: HIGHLIGHT disagreements
- <50%: ESCALATE to user

## Sub-agent dispatch

When ≥3 issues need auditing, dispatch one sub-agent per issue batch to triage, then consolidate; below that, triage
inline. Pick the mechanism per the shared Sub-Agent Selection Rules (`configs/claude/references/sub-agent-dispatch.md`):
native Task sub-agents on Claude, or `parallel_agent.py` / inline on other assistants. Dispatched sub-agents execute
their task directly and do not re-dispatch.
