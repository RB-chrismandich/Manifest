---
name: issue-triage
description: "Comprehensive issue audit for the configured tracker (GitHub, GitLab, Linear, or Jira): validate prioritization, identify duplicates and overlapping issues, detect stale/obsolete issues, produce clean actionable backlog"
---

# Issue Triage Skill

Automated issue backlog management for the configured tracker (GitHub, GitLab, Linear, or Jira) with duplicate detection, staleness analysis, and priority validation.

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
| `--close-stale` | Auto-close stale issues (requires explicit flag) | false |
| `--team TEAM` | Filter by team key (e.g., "ENG", "PRODUCT") — linear only; other providers filter by label/milestone instead | all teams |
| `--priority N` | Filter by priority (0-4) | all priorities |
| `--limit N` | Max issues to analyze | 500 |

## Prerequisites

1. **Tracker authentication** — per provider (resolved via `tracker_ops.sh resolve-provider`):
   - `linear`: `LINEAR_API_KEY` env var or `~/.config/linear/token`
   - `github` / `gitlab`: `gh` / `glab` CLI authenticated
   - `jira`: Atlassian MCP configured (jira is MCP-only — `tracker_ops.sh` exits 3 for any jira verb in shell context; run jira triage from agent context and call the Atlassian MCP tools directly instead of shelling out)
2. **Tools installed**: `jq`, `python3`
3. **Scripts available**: `~/.claude/scripts/tracker_ops.sh`, `~/.claude/scripts/parallel_agent.py`
4. **Config loaded**: `~/.claude/config/tracker_triage.yml`

## Workflow

### Step 1: Load Configuration

```bash
#!/bin/bash
set -euo pipefail

# Load triage configuration
CONFIG_FILE="${HOME}/.claude/config/tracker_triage.yml"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Configuration file not found: $CONFIG_FILE" >&2
    exit 1
fi

# Parse YAML config using python
read_config() {
    python3 << 'EOF'
import yaml, sys
with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

# Extract key thresholds
dup = config['duplicate_detection']
print(f"DUP_TITLE_HIGH={dup['title_similarity_high']}")
print(f"DUP_TITLE_MEDIUM={dup['title_similarity_medium']}")
print(f"STALENESS_DAYS={config['staleness']['inactivity_days']}")
print(f"FILE_MISSING_THRESHOLD={config['staleness']['file_missing_threshold']}")
print(f"CONSENSUS_HIGH={config['consensus']['high_threshold']}")
print(f"CONSENSUS_MEDIUM={config['consensus']['medium_threshold']}")
EOF
"$CONFIG_FILE"
}

# Source config as environment variables
config_string="$(read_config)"
while IFS= read -r line; do
    case "$line" in
        DUP_TITLE_HIGH=*)
            val="${line#*=}"; val="${val%\"}"; val="${val#\"}"; DUP_TITLE_HIGH="$val" ;;
        DUP_TITLE_MEDIUM=*)
            val="${line#*=}"; val="${val%\"}"; val="${val#\"}"; DUP_TITLE_MEDIUM="$val" ;;
        STALENESS_DAYS=*)
            val="${line#*=}"; val="${val%\"}"; val="${val#\"}"; STALENESS_DAYS="$val" ;;
        FILE_MISSING_THRESHOLD=*)
            val="${line#*=}"; val="${val%\"}"; val="${val#\"}"; FILE_MISSING_THRESHOLD="$val" ;;
        CONSENSUS_HIGH=*)
            val="${line#*=}"; val="${val%\"}"; val="${val#\"}"; CONSENSUS_HIGH="$val" ;;
        CONSENSUS_MEDIUM=*)
            val="${line#*=}"; val="${val%\"}"; val="${val#\"}"; CONSENSUS_MEDIUM="$val" ;;
    esac
done <<< "$config_string"

echo "Configuration loaded: DUP_TITLE_HIGH=$DUP_TITLE_HIGH, STALENESS_DAYS=$STALENESS_DAYS"
```

### Step 2: Fetch Issues

```bash
# Parse arguments
DRY_RUN=false
CLOSE_STALE=false
TEAM_FILTER=""
PRIORITY_FILTER=""
LIMIT=500

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --close-stale) CLOSE_STALE=true; shift ;;
        --team) TEAM_FILTER="$2"; shift 2 ;;
        --priority) PRIORITY_FILTER="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Fetch issues in each provider's native shape — normalized to a common
# schema in Step 3 before any duplicate/staleness/priority logic runs.
TEMP_DIR=$(mktemp -d)
RAW_ISSUES_FILE="$TEMP_DIR/raw_issues.json"

PROVIDER=$(~/.claude/scripts/tracker_ops.sh resolve-provider)
echo "Fetching issues from ${PROVIDER}..."

case "$PROVIDER" in
    github)
        # No "team" scope on issue-list; --team filters by label/milestone
        # instead (caller's responsibility — see Arguments table).
        ~/.claude/scripts/tracker_ops.sh issue-list --state open --limit "$LIMIT" \
            --json number,title,body,labels,createdAt,updatedAt,state \
            > "$RAW_ISSUES_FILE"
        ;;
    gitlab)
        ~/.claude/scripts/tracker_ops.sh issue-list --state opened --per-page "$LIMIT" \
            --output-format json \
            > "$RAW_ISSUES_FILE"
        ;;
    linear)
        # Linear models "team" as a first-class scope. team-list has no
        # tracker_ops.sh equivalent (engine-level, linear-only concept — it isn't
        # part of the canonical verb set), so it stays a direct linear_ops.sh call.
        if [[ -n "$TEAM_FILTER" ]]; then
            ~/.claude/scripts/tracker_ops.sh issue-list \
                --team "$TEAM_FILTER" \
                --limit "$LIMIT" \
                --json > "$RAW_ISSUES_FILE"
        else
            # Fetch across all teams, then merge the per-team arrays into one
            # (issue-list emits one JSON array per call; Step 3's normalizer
            # needs a single valid JSON array, not a concatenated stream).
            TEAM_PARTS="$TEMP_DIR/raw_issues_by_team.ndjson"
            : > "$TEAM_PARTS"
            ~/.claude/scripts/linear_ops.sh team-list --json | jq -r '.[].key' | while read -r team; do
                ~/.claude/scripts/tracker_ops.sh issue-list \
                    --team "$team" \
                    --limit "$LIMIT" \
                    --json >> "$TEAM_PARTS"
            done
            jq -s 'add // []' "$TEAM_PARTS" > "$RAW_ISSUES_FILE"
        fi
        ;;
    jira)
        # jira is MCP-only (tracker_ops.sh exits 3) — fetch via the Atlassian
        # MCP search tool (name resolved via
        # `~/.claude/scripts/tracker_registry.py mcp-tool jira search`,
        # currently `searchJiraIssuesUsingJql`) from agent context instead of
        # this shell block. Extract the `issues` array so $RAW_ISSUES_FILE is
        # a JSON list, consistent with the other providers.
        echo "Jira fetch is agent-context only; populate $RAW_ISSUES_FILE via the Atlassian MCP before continuing." >&2
        ;;
esac
```

### Step 3: Normalize to Common Schema

Every downstream step (duplicate detection, staleness, priority validation) reads only this
schema — never a provider's raw shape. Fields and their honest per-provider mappings:

| Field | Meaning | github | gitlab | linear | jira |
|-------|---------|--------|--------|--------|------|
| `id` | internal unique id | `number` (str) | `iid`/`id` (str) | `id` | `id`/`key` |
| `identifier` | human-facing id used by `tracker_ops.sh` verbs | `number` | `iid` | `identifier` | `key` |
| `title` | issue title | `title` | `title` | `title` | `fields.summary` |
| `description` | issue body | `body` | `description` | `description` | `fields.description` |
| `priority` | canonical 0-4 (1=Urgent…4=Low, 0=None — Linear's native scale, `tracker_triage.yml priority.labels`) | derived from priority-shaped labels (`urgent`/`p0`/`critical`/`blocker`→1, `high`/`p1`→2, `medium`/`p2`→3, `low`/`p3`/`p4`→4, else 0) | same label derivation as github | native `priority` field | derived from `fields.priority.name` (Highest/Blocker→1, High→2, Medium→3, Low/Lowest→4, else 0) |
| `state` | canonical workflow state (`backlog`/`started`/`completed`/`canceled`) | open + no status label→`backlog`; open + `in-progress`/`needs-review` label→`started`; closed→`completed` (or `canceled` if a `wontfix`/`duplicate`/`invalid` label is present) | same derivation as github | native `state.type` | `fields.status.statusCategory.key` (`new`→backlog, `indeterminate`→started, `done`→completed; a cancellation-worded resolution→`canceled`) |
| `team` | scope key used for the duplicate-detection same-scope boost | `""` (no native scope on issue-list; the boost is skipped when empty — Step 5) | `""` (same — no native scope) | `team.key` | `fields.project.key` |
| `labels` | label names | `labels[].name` | `labels[]` (already strings) | `labels.nodes[].name` | `fields.labels` |
| `createdAt` / `updatedAt` | ISO8601 timestamps | `createdAt`/`updatedAt` | `created_at`/`updated_at` | `createdAt`/`updatedAt` | `fields.created`/`fields.updated` |

`relations` (Linear's GraphQL `relations.nodes`) is dropped: no downstream step ever reads it,
and github/gitlab/jira have no clean equivalent worth inventing for a field nothing consumes.

```bash
echo "Normalizing issues to common schema..."

python3 - "$PROVIDER" "$RAW_ISSUES_FILE" << 'PYEOF' > "$TEMP_DIR/issues_normalized.json"
#!/usr/bin/env python3
"""Normalize per-provider issue JSON into the common triage schema."""
import json
import sys

provider = sys.argv[1]
with open(sys.argv[2]) as f:
    raw = json.load(f) or []

# Priority labels honored on github/gitlab (and as a jira fallback) when the
# tracker has no native 0-4 field. Mirrors Linear's own scale
# (tracker_triage.yml priority.labels): 1=Urgent 2=High 3=Medium 4=Low
# 0=None (no matching label — an honest default, not a guess).
PRIORITY_LABEL_MAP = {
    "urgent": 1, "p0": 1, "critical": 1, "blocker": 1,
    "high": 2, "p1": 2,
    "medium": 3, "p2": 3,
    "low": 4, "p3": 4, "p4": 4,
}

def priority_from_labels(labels):
    label_set = {l.lower() for l in labels}
    for label in label_set:
        for key, val in PRIORITY_LABEL_MAP.items():
            if key in label:
                return val
    return 0

# Canonical status labels (tracker_providers.yml status_map / tracker_ops.sh
# CANONICAL_STATUSES): planned, in-progress, needs-review, done.
def state_from_open_closed(is_closed, labels):
    label_set = {l.lower() for l in labels}
    if is_closed:
        if label_set & {"wontfix", "duplicate", "invalid"}:
            return "canceled"
        return "completed"
    if label_set & {"needs-review", "in-progress"}:
        return "started"
    return "backlog"

issues = []

for item in raw:
    if provider == "github":
        labels = [l["name"] for l in item.get("labels", [])]
        is_closed = str(item.get("state", "OPEN")).upper() == "CLOSED"
        number = str(item["number"])
        issue = {
            "id": number,
            "identifier": number,
            "title": item["title"],
            "description": item.get("body") or "",
            "priority": priority_from_labels(labels),
            "state": state_from_open_closed(is_closed, labels),
            "team": "",
            "labels": labels,
            "createdAt": item.get("createdAt", ""),
            "updatedAt": item.get("updatedAt", ""),
        }
    elif provider == "gitlab":
        labels = item.get("labels", [])
        is_closed = item.get("state", "opened") == "closed"
        number = str(item.get("iid", item.get("id", "")))
        issue = {
            "id": number,
            "identifier": number,
            "title": item["title"],
            "description": item.get("description") or "",
            "priority": priority_from_labels(labels),
            "state": state_from_open_closed(is_closed, labels),
            "team": "",
            "labels": labels,
            "createdAt": item.get("created_at", ""),
            "updatedAt": item.get("updated_at", ""),
        }
    elif provider == "linear":
        labels = [l["name"] for l in item.get("labels", {}).get("nodes", [])]
        issue = {
            "id": item.get("id", ""),
            "identifier": item.get("identifier", ""),
            "title": item["title"],
            "description": item.get("description") or "",
            "priority": item.get("priority", 0) or 0,
            "state": item.get("state", {}).get("type", "backlog"),
            "team": item.get("team", {}).get("key", ""),
            "labels": labels,
            "createdAt": item.get("createdAt", ""),
            "updatedAt": item.get("updatedAt", ""),
        }
    elif provider == "jira":
        fields = item.get("fields", {})
        labels = fields.get("labels") or []
        status_category = (fields.get("status") or {}).get("statusCategory", {}).get("key", "new")
        resolution_name = ((fields.get("resolution") or {}).get("name") or "").lower()
        if resolution_name in ("won't do", "wont do", "cancelled", "canceled"):
            state = "canceled"
        elif status_category == "done":
            state = "completed"
        elif status_category == "indeterminate":
            state = "started"
        else:
            state = "backlog"
        priority_name = ((fields.get("priority") or {}).get("name") or "").lower()
        priority = {
            "highest": 1, "blocker": 1,
            "high": 2,
            "medium": 3,
            "low": 4, "lowest": 4,
        }.get(priority_name, 0)
        key = item.get("key", "")
        issue = {
            "id": item.get("id", key),
            "identifier": key,
            "title": fields.get("summary", ""),
            "description": fields.get("description") or "",
            "priority": priority,
            "state": state,
            "team": (fields.get("project") or {}).get("key", ""),
            "labels": labels,
            "createdAt": fields.get("created", ""),
            "updatedAt": fields.get("updated", ""),
        }
    else:
        continue

    issues.append(issue)

print(json.dumps(issues, indent=2))
PYEOF

# Apply priority filter if specified (uniform 0-4 scale, applied
# post-normalization so it works the same across every provider)
if [[ -n "$PRIORITY_FILTER" ]]; then
    jq --argjson pri "$PRIORITY_FILTER" '[.[] | select(.priority == $pri)]' \
        "$TEMP_DIR/issues_normalized.json" > "$TEMP_DIR/issues.json"
else
    cp "$TEMP_DIR/issues_normalized.json" "$TEMP_DIR/issues.json"
fi

ISSUE_COUNT=$(jq 'length' "$TEMP_DIR/issues.json")
echo "Fetched $ISSUE_COUNT issues (normalized)"
```

### Step 4: Extract Components

```bash
echo "Extracting components from issue descriptions..."

extract_components() {
    local description="$1"

    # Extract file paths from markdown code blocks
    local file_paths=$(echo "$description" | grep -oE '`[^`]+\.(py|js|ts|go|sh|java|rb|md|yml|yaml|json|toml)`' | tr -d '`' | paste -sd ',' -)

    # Extract service/component mentions
    local services=$(echo "$description" | grep -oiE '(api|service|module|component|package|library|framework|database|auth|frontend|backend)-[a-z0-9_-]+' | paste -sd ',' -)

    echo "${file_paths},${services}"
}

jq -c '.[]' "$TEMP_DIR/issues.json" | while read -r issue; do
    description=$(echo "$issue" | jq -r '.description // ""')
    components=$(extract_components "$description")

    echo "$issue" | jq --arg comps "$components" '.components = ($comps | split(",") | map(select(length > 0)))'
done > "$TEMP_DIR/issues_with_components.json"
```

### Step 5: Duplicate Detection

```bash
echo "Detecting duplicates..."

DUPLICATES_FILE="$TEMP_DIR/duplicates.json"

detect_duplicates() {
    local issues_file="$1"

    # Python script for fuzzy title matching
    python3 << 'PYEOF'
import json
import sys
from difflib import SequenceMatcher

def similarity(a, b):
    """Calculate string similarity ratio"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# Load issues
with open(sys.argv[1]) as f:
    issues = json.load(f)

duplicates = []

# Compare all pairs
for i, issue_a in enumerate(issues):
    for j, issue_b in enumerate(issues[i+1:], start=i+1):
        title_a = issue_a['title']
        title_b = issue_b['title']

        title_sim = similarity(title_a, title_b)

        # Calculate description overlap (if both exist)
        desc_sim = 0.0
        if issue_a.get('description') and issue_b.get('description'):
            desc_sim = similarity(issue_a['description'], issue_b['description'])

        # Boost score for same team/scope (github/gitlab have no native
        # scope — team is "" for every issue there — so an empty match never
        # counts; only a real, non-empty shared team/project key boosts)
        same_team_boost = 0.05 if issue_a['team'] and issue_a['team'] == issue_b['team'] else 0.0

        # Boost score for shared labels
        shared_labels = set(issue_a.get('labels', [])) & set(issue_b.get('labels', []))
        label_boost = len(shared_labels) * 0.05

        # Combined score (weighted average)
        combined_score = (title_sim * 0.7) + (desc_sim * 0.3) + same_team_boost + label_boost

        # Categorize by threshold
        dup_high = float(sys.argv[2])
        dup_medium = float(sys.argv[3])

        if combined_score >= dup_high:
            confidence = "HIGH"
        elif combined_score >= dup_medium:
            confidence = "MEDIUM"
        else:
            continue  # Skip low similarity

        duplicates.append({
            "primary_issue": {
                "id": issue_a['id'],
                "identifier": issue_a['identifier'],
                "title": issue_a['title'],
                "created_at": issue_a['createdAt']
            },
            "duplicate_issue": {
                "id": issue_b['id'],
                "identifier": issue_b['identifier'],
                "title": issue_b['title'],
                "created_at": issue_b['createdAt']
            },
            "similarity_score": round(combined_score, 3),
            "title_similarity": round(title_sim, 3),
            "description_similarity": round(desc_sim, 3),
            "confidence": confidence,
            "needs_agent_review": confidence == "MEDIUM"
        })

# Output duplicates
print(json.dumps(duplicates, indent=2))
PYEOF
"$TEMP_DIR/issues_with_components.json" "$DUP_TITLE_HIGH" "$DUP_TITLE_MEDIUM"
}

detect_duplicates "$TEMP_DIR/issues_with_components.json" > "$DUPLICATES_FILE"

# For MEDIUM confidence duplicates, use parallel agents
echo "Verifying medium-confidence duplicates with parallel agents..."

jq -c '.[] | select(.needs_agent_review == true)' "$DUPLICATES_FILE" | while read -r dup; do
    primary_title=$(echo "$dup" | jq -r '.primary_issue.title')
    duplicate_title=$(echo "$dup" | jq -r '.duplicate_issue.title')
    primary_desc=$(jq -r --arg id "$(echo "$dup" | jq -r '.primary_issue.identifier')" \
        '.[] | select(.identifier == $id) | .description // ""' "$TEMP_DIR/issues_with_components.json")
    duplicate_desc=$(jq -r --arg id "$(echo "$dup" | jq -r '.duplicate_issue.identifier')" \
        '.[] | select(.identifier == $id) | .description // ""' "$TEMP_DIR/issues_with_components.json")

    # Call parallel agents for consensus
    consensus=$(~/.claude/scripts/parallel_agent.py --json --timeout 300 \
        --cursor-model mini --claude-model haiku \
        "Are these issues duplicates?

        Issue A: $primary_title
        Description A: $primary_desc

        Issue B: $duplicate_title
        Description B: $duplicate_desc

        Return JSON: {\"is_duplicate\": true/false, \"confidence\": 0-100, \"reasoning\": \"...\"}")

    consensus_score=$(echo "$consensus" | jq -r '.cross_verification.consensus_score // 0')
    is_duplicate=$(echo "$consensus" | jq -r '.agents.claude.output' | jq -r '.is_duplicate // false')

    # Update confidence based on consensus
    if [[ "$is_duplicate" == "true" && $consensus_score -ge 80 ]]; then
        # Promote to HIGH confidence
        jq --arg id1 "$(echo "$dup" | jq -r '.primary_issue.identifier')" \
           --arg id2 "$(echo "$dup" | jq -r '.duplicate_issue.identifier')" \
           '(.[] | select(.primary_issue.identifier == $id1 and .duplicate_issue.identifier == $id2) | .confidence) = "HIGH"' \
           "$DUPLICATES_FILE" > "$TEMP_DIR/dups_updated.json"
        mv "$TEMP_DIR/dups_updated.json" "$DUPLICATES_FILE"
    fi
done

DUP_COUNT=$(jq '[.[] | select(.confidence == "HIGH")] | length' "$DUPLICATES_FILE")
echo "Found $DUP_COUNT high-confidence duplicates"
```

### Step 6: Staleness Detection

```bash
echo "Detecting stale issues..."

STALE_FILE="$TEMP_DIR/stale.json"

detect_stale() {
    local issues_file="$1"

    python3 << 'PYEOF'
import json
import sys
import os
from datetime import datetime, timezone

# Load issues
with open(sys.argv[1]) as f:
    issues = json.load(f)

staleness_days = int(sys.argv[2])
file_missing_threshold = float(sys.argv[3])
current_time = datetime.now(timezone.utc)

stale_issues = []

for issue in issues:
    stale_reasons = []

    # Check inactivity
    updated_at = datetime.fromisoformat(issue['updatedAt'].replace('Z', '+00:00'))
    days_since_update = (current_time - updated_at).days

    if days_since_update > staleness_days and issue['priority'] == 0 and len(issue.get('labels', [])) == 0:
        stale_reasons.append(f"No activity for {days_since_update} days, no priority, no labels")

    # Check for deleted file references
    description = issue.get('description', '')
    if description:
        # Extract file paths from description
        import re
        file_paths = re.findall(r'`([^`]+\.(py|js|ts|go|sh|java|rb|md|yml|yaml|json|toml))`', description)

        if file_paths:
            missing_count = 0
            total_count = len(file_paths)

            for file_path, _ in file_paths:
                # Expand ~ to home directory
                expanded_path = os.path.expanduser(file_path)
                if not os.path.exists(expanded_path):
                    missing_count += 1

            if total_count > 0:
                missing_ratio = missing_count / total_count
                if missing_ratio > file_missing_threshold:
                    stale_reasons.append(f"{missing_count}/{total_count} referenced files deleted ({int(missing_ratio*100)}%)")

    # Check for "planned" label - NEVER auto-close if present
    has_planned_label = 'planned' in [label.lower() for label in issue.get('labels', [])]

    if stale_reasons and not has_planned_label:
        stale_issues.append({
            "id": issue['id'],
            "identifier": issue['identifier'],
            "title": issue['title'],
            "team": issue['team'],
            "updated_at": issue['updatedAt'],
            "days_since_update": days_since_update,
            "reasons": stale_reasons,
            "confidence": "HIGH",
            "safe_to_close": not has_planned_label
        })
    elif stale_reasons and has_planned_label:
        # Log but don't close
        stale_issues.append({
            "id": issue['id'],
            "identifier": issue['identifier'],
            "title": issue['title'],
            "team": issue['team'],
            "updated_at": issue['updatedAt'],
            "days_since_update": days_since_update,
            "reasons": stale_reasons + ["HAS 'planned' LABEL - DO NOT AUTO-CLOSE"],
            "confidence": "HIGH",
            "safe_to_close": False
        })

# Output stale issues
print(json.dumps(stale_issues, indent=2))
PYEOF
"$TEMP_DIR/issues_with_components.json" "$STALENESS_DAYS" "$FILE_MISSING_THRESHOLD"
}

detect_stale "$TEMP_DIR/issues_with_components.json" > "$STALE_FILE"

STALE_COUNT=$(jq '[.[] | select(.safe_to_close == true)] | length' "$STALE_FILE")
echo "Found $STALE_COUNT closable stale issues"
```

### Step 7: Priority Validation

```bash
echo "Validating issue priorities..."

PRIORITY_FILE="$TEMP_DIR/priority_issues.json"

validate_priorities() {
    local issues_file="$1"

    # Use parallel agents for complex priority scoring
    jq -c '.[] | select(.priority != null)' "$issues_file" | while read -r issue; do
        identifier=$(echo "$issue" | jq -r '.identifier')
        title=$(echo "$issue" | jq -r '.title')
        description=$(echo "$issue" | jq -r '.description // ""')
        current_priority=$(echo "$issue" | jq -r '.priority')

        # Call parallel agents for priority scoring
        consensus=$(~/.claude/scripts/parallel_agent.py --json --timeout 300 \
            --cursor-model flash --claude-model sonnet \
            "Score this issue for prioritization:

            Title: $title
            Description: $description
            Current priority: $current_priority (0=None, 1=Urgent, 2=High, 3=Medium, 4=Low)

            Rate on scale 1-5:
            - Impact: User/business impact if not addressed
            - Urgency: Time sensitivity
            - Readiness: Prerequisites/dependencies ready
            - Risk: Implementation risk/complexity

            Calculate score: (Impact × 3) + (Urgency × 2) + (Readiness × 2) - Risk

            Return JSON with:
            - impact_score: 1-5
            - urgency_score: 1-5
            - readiness_score: 1-5
            - risk_score: 1-5
            - total_score: calculated value
            - recommended_priority: 0-4 (based on score thresholds: 28+=1, 22+=2, 16+=3, 10+=4, <10=0)
            - reasoning: brief explanation")

        # Parse consensus
        consensus_score=$(echo "$consensus" | jq -r '.cross_verification.consensus_score // 0')

        # Extract recommendation from agent output
        claude_output=$(echo "$consensus" | jq -r '.agents.claude.output // "{}"')
        recommended_priority=$(echo "$claude_output" | jq -r '.recommended_priority // null')

        if [[ "$recommended_priority" != "null" && "$recommended_priority" != "$current_priority" && $consensus_score -ge 70 ]]; then
            echo "{
                \"identifier\": \"$identifier\",
                \"title\": \"$title\",
                \"current_priority\": $current_priority,
                \"recommended_priority\": $recommended_priority,
                \"consensus_score\": $consensus_score,
                \"reasoning\": $(echo "$claude_output" | jq -r '.reasoning // "N/A"' | jq -Rs .)
            }"
        fi
    done | jq -s . > "$PRIORITY_FILE"
}

validate_priorities "$TEMP_DIR/issues_with_components.json"

PRIORITY_COUNT=$(jq 'length' "$PRIORITY_FILE")
echo "Found $PRIORITY_COUNT priority misalignments"
```

### Step 8: Generate Recommendations

```bash
echo "Generating triage report..."

REPORT_FILE="$TEMP_DIR/triage_report.md"

cat > "$REPORT_FILE" << EOFMD
# Issue Triage Report ($PROVIDER)

**Generated**: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Mode**: $([ "$DRY_RUN" = true ] && echo "DRY-RUN" || echo "LIVE")
**Issues Analyzed**: $ISSUE_COUNT
**Team Filter**: ${TEAM_FILTER:-All teams}

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Total issues analyzed | $ISSUE_COUNT |
| High-confidence duplicates | $(jq '[.[] | select(.confidence == "HIGH")] | length' "$DUPLICATES_FILE") |
| Medium-confidence duplicates (needs review) | $(jq '[.[] | select(.confidence == "MEDIUM")] | length' "$DUPLICATES_FILE") |
| Stale issues (safe to close) | $(jq '[.[] | select(.safe_to_close == true)] | length' "$STALE_FILE") |
| Stale issues (has 'planned' label) | $(jq '[.[] | select(.safe_to_close == false)] | length' "$STALE_FILE") |
| Priority misalignments | $PRIORITY_COUNT |

---

## High Confidence Duplicates (Auto-mark)

These duplicates have ≥${DUP_TITLE_HIGH} similarity and can be auto-marked:

$(jq -r '.[] | select(.confidence == "HIGH") |
"- **\(.duplicate_issue.identifier)** → \(.primary_issue.identifier)
  - Similarity: \(.similarity_score * 100)%
  - Primary: \(.primary_issue.title)
  - Duplicate: \(.duplicate_issue.title)"' "$DUPLICATES_FILE")

---

## Stale Issues (Safe to Close)

These issues meet staleness criteria and can be closed with \`--close-stale\`:

$(jq -r '.[] | select(.safe_to_close == true) |
"- **\(.identifier)** (\(.team)) - \(.days_since_update) days inactive
  - Title: \(.title)
  - Reasons: \(.reasons | join("; "))"' "$STALE_FILE")

---

## Stale Issues (Protected by 'planned' Label)

These issues are stale but have the 'planned' label - **DO NOT AUTO-CLOSE**:

$(jq -r '.[] | select(.safe_to_close == false) |
"- **\(.identifier)** (\(.team)) - \(.days_since_update) days inactive
  - Title: \(.title)
  - Reasons: \(.reasons | join("; "))
  - Action: Manual review required"' "$STALE_FILE")

---

## Priority Misalignments (Recommended Updates)

These issues have priority misalignments based on impact/urgency scoring:

$(jq -r '.[] |
"- **\(.identifier)**: Current P\(.current_priority) → Recommended P\(.recommended_priority) (Consensus: \(.consensus_score)%)
  - Title: \(.title)
  - Reasoning: \(.reasoning)"' "$PRIORITY_FILE")

---

## Next Steps

EOFMD

if [ "$DRY_RUN" = true ]; then
    cat >> "$REPORT_FILE" << EOFMD
**DRY-RUN MODE** - No actions taken. To execute:

1. Review recommendations above
2. Re-run without \`--dry-run\` to mark duplicates
3. Add \`--close-stale\` flag to close stale issues
EOFMD
else
    cat >> "$REPORT_FILE" << EOFMD
**Actions to be executed:**

- Mark $(jq '[.[] | select(.confidence == "HIGH")] | length' "$DUPLICATES_FILE") high-confidence duplicates
$([ "$CLOSE_STALE" = true ] && echo "- Close $(jq '[.[] | select(.safe_to_close == true)] | length' "$STALE_FILE") stale issues" || echo "- Stale issues NOT closed (use --close-stale to enable)")
- Priority updates require manual approval (use the tracker's UI/CLI — Linear UI, gh/glab, or Jira)
EOFMD
fi

cat "$REPORT_FILE"
```

### Step 9: Execute Actions

```bash
if [ "$DRY_RUN" = false ]; then
    echo ""
    echo "=== Executing Triage Actions ==="

    ACTIONS_LOG="$TEMP_DIR/actions.json"
    echo "[]" > "$ACTIONS_LOG"

    # Mark high-confidence duplicates
    echo "Marking duplicates..."
    jq -c '.[] | select(.confidence == "HIGH")' "$DUPLICATES_FILE" | while read -r dup; do
        duplicate_id=$(echo "$dup" | jq -r '.duplicate_issue.identifier')
        primary_id=$(echo "$dup" | jq -r '.primary_issue.identifier')

        ~/.claude/scripts/tracker_ops.sh duplicate-mark "$duplicate_id" --duplicate-of "$primary_id"

        # Log action
        jq --arg action "mark_duplicate" \
           --arg issue "$duplicate_id" \
           --arg target "$primary_id" \
           '. += [{action: $action, issue: $issue, target: $target, timestamp: now}]' \
           "$ACTIONS_LOG" > "$TEMP_DIR/actions_tmp.json"
        mv "$TEMP_DIR/actions_tmp.json" "$ACTIONS_LOG"

        echo "  ✓ Marked $duplicate_id as duplicate of $primary_id"
    done

    # Close stale issues (only if --close-stale flag)
    if [ "$CLOSE_STALE" = true ]; then
        echo "Closing stale issues..."
        jq -c '.[] | select(.safe_to_close == true)' "$STALE_FILE" | while read -r stale; do
            issue_id=$(echo "$stale" | jq -r '.identifier')
            reasons=$(echo "$stale" | jq -r '.reasons | join("; ")')

            ~/.claude/scripts/tracker_ops.sh issue-close "$issue_id" \
                --comment "Closing as stale: $reasons. Reopen if still relevant."

            # Log action
            jq --arg action "close_stale" \
               --arg issue "$issue_id" \
               --arg reason "$reasons" \
               '. += [{action: $action, issue: $issue, reason: $reason, timestamp: now}]' \
               "$ACTIONS_LOG" > "$TEMP_DIR/actions_tmp.json"
            mv "$TEMP_DIR/actions_tmp.json" "$ACTIONS_LOG"

            echo "  ✓ Closed $issue_id (stale)"
        done
    else
        echo "Stale issue closure SKIPPED (use --close-stale to enable)"
    fi

    # Output action audit
    echo ""
    echo "=== Action Audit Trail ==="
    jq -r '.[] | "[\(.timestamp | todate)] \(.action): \(.issue) \(.target // .reason // "")"' "$ACTIONS_LOG"

    # Copy audit to permanent location
    AUDIT_DIR="${HOME}/.claude/.agent_outputs/triage_audits"
    mkdir -p "$AUDIT_DIR"
    cp "$ACTIONS_LOG" "$AUDIT_DIR/triage_$(date +%Y%m%d_%H%M%S).json"
    echo "Audit saved to $AUDIT_DIR"
fi

# Cleanup
echo ""
echo "Triage complete. Report saved to: $REPORT_FILE"
```

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

if [[ ! -x ~/.claude/scripts/tracker_ops.sh ]]; then
    echo "Error: tracker_ops.sh not found or not executable" >&2
    exit 1
fi

if [[ ! -f ~/.claude/config/tracker_triage.yml ]]; then
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
