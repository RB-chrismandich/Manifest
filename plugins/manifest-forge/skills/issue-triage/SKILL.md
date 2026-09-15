---
name: issue-triage
description: "Full issue audit for the configured tracker (GitHub, GitLab, Linear, or Jira): validate prioritization, identify duplicates and overlapping issues, detect stale/obsolete issues, produce clean actionable backlog"
---

# Issue Triage Skill

Automated issue backlog management for the configured tracker (GitHub, GitLab, Linear, or
Jira) with duplicate detection, staleness analysis, and priority validation.

## Purpose

This skill performs comprehensive issue triage by:

1. Detecting duplicate issues using semantic similarity
2. Identifying stale/obsolete issues (deleted file references, long inactivity)
3. Validating priority alignment with impact/urgency
4. Using OMP-native reviewer waves for ambiguous duplicate and priority decisions
5. Generating actionable recommendations with explicit verdict evidence

## Arguments

```bash
/issue-triage [--dry-run] [--close-stale] [--team TEAM] [--priority N] [--limit N]
```

| Argument | Description | Default |
|----------|-------------|---------|
| `--dry-run` | Analysis only, no mutations | false |
| `--close-stale` | Auto-close stale issues (requires explicit flag) | false |
| `--team TEAM` | Filter by team key (e.g., "ENG", "PRODUCT") — linear only; other providers filter by label/milestone instead | all teams |
| `--priority N` | Filter by priority (0-4) | all priorities |
| `--limit N` | Max issues to analyze | 500 |

## Prerequisites

1. **Tracker authentication** — per provider (resolved via `tracker_ops.sh resolve-provider`):
   - `linear`: `LINEAR_API_KEY` environment variable or native harness/MCP auth
   - `github` / `gitlab`: `gh` / `glab` CLI authenticated
   - `jira`: Atlassian MCP configured (jira is MCP-only — `tracker_ops.sh` exits 3 for any jira verb in
     shell context; run jira triage from agent context and call the Atlassian MCP tools directly instead
     of shelling out)
2. **Tools installed**: `jq`, `python3`, plus OMP `task` for reviewer waves
3. **Scripts available**: `../../runtime/bin/tracker_ops.sh`
4. **Config loaded**: `../../runtime/config/tracker_triage.json`

## Workflow

The full step-by-step workflow — including the exact scripts to run at each step — lives in
[references/workflow.md](references/workflow.md). **Read that file and execute each step in order in one shell
session** (later steps consume env vars and intermediate files set by earlier ones). Steps:

1. Step 1: Load Configuration
2. Step 2: Fetch Issues
3. Step 3: Normalize to Common Schema
4. Step 4: Extract Components
5. Step 5: Duplicate Detection
6. Step 6: Staleness Detection
7. Step 7: Priority Validation
8. Step 8: Generate Recommendations
9. Step 9: Execute Actions

## Safety Rules

1. **Never auto-close issues with "planned" label** - these are intentionally kept in backlog
2. **Promote a MEDIUM duplicate only with three valid reviewer verdicts and ≥80% duplicate votes**
3. **Change a priority recommendation only with three valid verdicts and ≥70% modal agreement**
4. **Verify file deletion before marking stale** - check if files truly don't exist
5. **Require explicit --close-stale flag** - no accidental closures
6. **Log all actions to audit trail** - full accountability

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

if [[ ! -x ../../runtime/bin/tracker_ops.sh ]]; then
    echo "Error: tracker_ops.sh not found or not executable" >&2
    exit 1
fi

if [[ ! -f ../../runtime/config/tracker_triage.json ]]; then
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
- **JSON audit log** in `$XDG_STATE_HOME/manifest/forge/triage_audits/`
- **Action summary** with counts and recommendations

## OMP reviewer waves

The parent dispatches OMP-native, read-only `reviewer` tasks only for:

1. **MEDIUM-confidence duplicates** — five reviewers per pair return the
   duplicate verdict schema from Step 5.
2. **Priority validation** — five reviewers per candidate return the priority
   verdict schema from Step 7.

Dispatch each independent wave in one `task` call, with at most 32 task items
per wave. Children execute one assigned review and never redispatch. The parent
validates every structured result, excludes and names invalid results, applies
the configured quorum and thresholds, and aggregates the evidence. If OMP
`task` is unavailable, execute the review inline and report `DEGRADED`; never
fall back to a provider CLI or model-specific dispatch.

## Sub-agent dispatch

This skill uses the shared OMP dispatch contract in
`../../runtime/references/sub-agent-dispatch.md`: submit all ready independent
units in one `task` call, in waves of at most 32; children execute directly and
never redispatch; use `hub` only to coordinate or wait; and the parent validates
and aggregates evidence. If `task` is unavailable, work inline and report
`DEGRADED`.
