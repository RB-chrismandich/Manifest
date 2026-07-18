# issue-prioritize: Full Workflow

The complete step-by-step procedure for this skill. Execute each step in order in the same shell session — later steps depend on env vars and intermediate files produced by earlier ones.

## Contents

- Step 1: Detect Platform
- Step 2: Fetch Open Issues
- Step 3: Normalize
- Step 4: Heuristic Pre-Scoring
- Step 5: Agent-Refined Scoring for Top Candidates
- Step 6: Codebase Context Validation (Optional)
- Step 7: Generate Report
- Step 8: STOP

## Workflow

### Step 1: Detect Platform

```bash
# Auto-detect platform from git remote
PLATFORM="${FORCED_PLATFORM:-$(~/.claude/scripts/git_platform.sh 2>/dev/null || echo "github")}"

# Validate platform CLI is available
case "$PLATFORM" in
    github)
        if ! command -v gh &>/dev/null; then
            echo "Error: gh CLI required for GitHub. Install: brew install gh" >&2
            exit 1
        fi
        ;;
    gitlab)
        if ! command -v glab &>/dev/null; then
            echo "Error: glab CLI required for GitLab. Install: brew install glab" >&2
            exit 1
        fi
        ;;
    linear)
        if [[ ! -x ~/.claude/scripts/linear_ops.sh ]]; then
            echo "Error: linear_ops.sh not found" >&2
            exit 1
        fi
        ;;
esac

echo "Platform detected: $PLATFORM"
```

### Step 2: Fetch Open Issues

Fetch issues using the appropriate platform CLI. Normalize output to a common JSON schema.

#### GitHub

```bash
REPO_FLAG=""
[[ -n "$REPO_ARG" ]] && REPO_FLAG="-R $REPO_ARG"

LABEL_FLAG=""
[[ "$FILTER_ALL" != true && -n "$FILTER_LABEL" ]] && LABEL_FLAG="--label $FILTER_LABEL"

gh issue list --state open --limit "$LIMIT" \
    --json number,title,labels,createdAt,updatedAt,body,comments,assignees \
    $REPO_FLAG $LABEL_FLAG > "$TEMP_DIR/raw_issues.json"
```

#### GitLab

```bash
REPO_FLAG=""
[[ -n "$REPO_ARG" ]] && REPO_FLAG="--repo $REPO_ARG"

LABEL_FLAG=""
[[ "$FILTER_ALL" != true && -n "$FILTER_LABEL" ]] && LABEL_FLAG="--label $FILTER_LABEL"

glab issue list --state opened --per-page "$LIMIT" \
    --output-format json \
    $REPO_FLAG $LABEL_FLAG > "$TEMP_DIR/raw_issues.json"
```

#### Linear

```bash
TEAM_FLAG=""
[[ -n "$TEAM_ARG" ]] && TEAM_FLAG="--team $TEAM_ARG"

LABEL_FLAG=""
[[ "$FILTER_ALL" != true && -n "$FILTER_LABEL" ]] && LABEL_FLAG="--label $FILTER_LABEL"

~/.claude/scripts/linear_ops.sh issue-list \
    --limit "$LIMIT" \
    --json $TEAM_FLAG $LABEL_FLAG > "$TEMP_DIR/raw_issues.json"
```

### Step 3: Normalize

Normalize all platform outputs to a common schema.

Label filtering is handled at fetch time (Step 2) via `--label`. If `--all` is set,
all open issues are fetched without a label filter.

```python
#!/usr/bin/env python3
"""Normalize issues from different platforms into a common schema."""
import json
import sys
from datetime import datetime, timezone

platform = sys.argv[1]

with open(sys.argv[2]) as f:
    raw = json.load(f)

issues = []

for item in raw:
    # Platform-specific field mapping
    if platform == "github":
        labels = [l["name"] for l in item.get("labels", [])]
        issue = {
            "number": item["number"],
            "title": item["title"],
            "body": item.get("body", ""),
            "labels": labels,
            "created_at": item["createdAt"],
            "updated_at": item["updatedAt"],
            "assignees": [a.get("login", "") for a in item.get("assignees", [])],
            "comment_count": len(item.get("comments", [])),
            "platform": "github",
        }
    elif platform == "gitlab":
        labels = item.get("labels", [])
        issue = {
            "number": item.get("iid", item.get("id")),
            "title": item["title"],
            "body": item.get("description", ""),
            "labels": labels,
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "assignees": [a.get("username", "") for a in item.get("assignees", [])],
            "comment_count": item.get("user_notes_count", 0),
            "platform": "gitlab",
        }
    elif platform == "linear":
        labels = [l["name"] for l in item.get("labels", {}).get("nodes", [])]
        issue = {
            "number": item.get("identifier", item.get("number", "")),
            "title": item["title"],
            "body": item.get("description", ""),
            "labels": labels,
            "created_at": item.get("createdAt", ""),
            "updated_at": item.get("updatedAt", ""),
            "assignees": [],
            "comment_count": 0,
            "platform": "linear",
        }
    else:
        continue

    issues.append(issue)

print(json.dumps(issues, indent=2))
```

Save normalized issues to `$TEMP_DIR/issues.json`.

### Step 4: Heuristic Pre-Scoring

Apply local heuristic scoring to every issue for initial ranking. This avoids
calling parallel agents for the full list.

```python
#!/usr/bin/env python3
"""Heuristic pre-scoring for issue prioritization."""
import json
import re
import sys
from datetime import datetime, timezone

with open(sys.argv[1]) as f:
    issues = json.load(f)

# Type detection keywords
TYPE_PATTERNS = {
    "bug": r"\b(bug|broken|crash|error|fail|fix|regression|wrong)\b",
    "feature": r"\b(add|new feature|implement|introduce|proposal)\b",
    "enhancement": r"\b(enhance|improve|upgrade|update|refactor|optimize)\b",
    "test": r"\b(test|coverage|spec|assertion|mock)\b",
    "tech-debt": r"\b(tech.?debt|cleanup|deprecat|legacy|migration|refactor)\b",
    "docs": r"\b(doc|readme|guide|tutorial|comment)\b",
    "infra": r"\b(ci|cd|deploy|docker|kubernetes|terraform|pipeline|infra)\b",
}

# Label-based scoring hints
LABEL_IMPACT = {
    "critical": 5, "blocker": 5, "high": 4, "priority": 4,
    "medium": 3, "low": 2, "minor": 1, "cosmetic": 1,
    "security": 5, "data-loss": 5, "performance": 3,
}

LABEL_URGENCY = {
    "urgent": 5, "critical": 5, "blocker": 4, "hotfix": 5,
    "p0": 5, "p1": 4, "p2": 3, "p3": 2, "p4": 1,
}

def detect_type(title, body, labels):
    """Detect issue type from title, body, and labels."""
    text = f"{title} {body}".lower()
    label_set = {l.lower() for l in labels}

    # Label-based detection (highest priority)
    for label in label_set:
        if "bug" in label:
            return "bug"
        if "feature" in label:
            return "feature"
        if "enhancement" in label:
            return "enhancement"
        if "test" in label:
            return "test"
        if "infra" in label or "ci" in label:
            return "infra"
        if "doc" in label:
            return "docs"

    # Pattern-based detection
    for issue_type, pattern in TYPE_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return issue_type

    return "feature"  # default

def heuristic_score(issue):
    """Calculate heuristic scores for an issue."""
    title = issue["title"].lower()
    body = (issue.get("body") or "").lower()
    labels = issue.get("labels", [])
    label_set = {l.lower() for l in labels}

    # Impact: from labels, keywords, and body length
    impact = 3  # default
    for label in label_set:
        for key, val in LABEL_IMPACT.items():
            if key in label:
                impact = max(impact, val)
                break
    if any(w in title for w in ["crash", "data loss", "security", "auth"]):
        impact = max(impact, 5)
    elif any(w in title for w in ["error", "fail", "broken"]):
        impact = max(impact, 4)

    # Urgency: from labels and age
    urgency = 2  # default
    for label in label_set:
        for key, val in LABEL_URGENCY.items():
            if key in label:
                urgency = max(urgency, val)
                break
    if any(w in title for w in ["urgent", "hotfix", "asap", "critical"]):
        urgency = max(urgency, 5)

    # Readiness: from body detail and labels
    readiness = 3  # default
    if "planned" in label_set:
        readiness = max(readiness, 5)
    if len(body) > 500:
        readiness = max(readiness, 4)  # detailed description
    elif len(body) < 50:
        readiness = min(readiness, 2)  # vague
    if re.search(r"##\s*(implementation|steps|plan|approach)", body):
        readiness = 5  # has an implementation plan

    # Risk: from scope indicators
    risk = 2  # default
    if re.search(r"(breaking change|migration|schema|database)", body):
        risk = max(risk, 4)
    if re.search(r"(multi.?service|cross.?service|all services)", body):
        risk = max(risk, 4)
    if re.search(r"(auth|payment|billing|credential)", body):
        risk = max(risk, 4)
    file_refs = re.findall(r"`[^`]+\.\w+`", body)
    if len(file_refs) > 5:
        risk = max(risk, 3)  # touches many files

    # Clamp all values to 1-5
    impact = max(1, min(5, impact))
    urgency = max(1, min(5, urgency))
    readiness = max(1, min(5, readiness))
    risk = max(1, min(5, risk))

    # Priority score = (Impact * 3) + (Urgency * 2) + (Readiness * 2) - Risk
    score = (impact * 3) + (urgency * 2) + (readiness * 2) - risk

    return {
        "impact": impact,
        "urgency": urgency,
        "readiness": readiness,
        "risk": risk,
        "score": score,
        "type": detect_type(issue["title"], issue.get("body", ""), labels),
    }

# Score all issues
scored = []
for issue in issues:
    scores = heuristic_score(issue)
    issue["scores"] = scores
    scored.append(issue)

# Sort by score descending, with tiebreakers
def sort_key(issue):
    s = issue["scores"]
    type_priority = 0 if s["type"] == "bug" else 1
    has_plan = 0 if "planned" in {l.lower() for l in issue.get("labels", [])} else 1
    created = issue.get("created_at", "9999")
    return (-s["score"], type_priority, has_plan, created)

scored.sort(key=sort_key)

print(json.dumps(scored, indent=2))
```

Save scored and sorted issues to `$TEMP_DIR/scored_issues.json`.

### Step 5: Agent-Refined Scoring for Top Candidates

For the top N+2 candidates (default: top 7), use parallel agents for refined scoring.
This provides multi-perspective validation of the heuristic rankings.

```bash
# Extract top candidates
TOP_COUNT=$((TOP_N + 2))
jq ".[:$TOP_COUNT]" "$TEMP_DIR/scored_issues.json" > "$TEMP_DIR/top_candidates.json"

# Load optional project context
PROJECT_CONTEXT=""
if [[ -n "$PROJECT_CONTEXT_FILE" && -f "$PROJECT_CONTEXT_FILE" ]]; then
    PROJECT_CONTEXT=$(cat "$PROJECT_CONTEXT_FILE")
fi

# Build scoring prompt
CANDIDATES=$(jq -r '.[] | "### #\(.number) — \(.title)\nBody: \(.body // "No description" | .[0:300])\nLabels: \(.labels | join(", "))\nHeuristic scores: Impact=\(.scores.impact) Urgency=\(.scores.urgency) Readiness=\(.scores.readiness) Risk=\(.scores.risk) Score=\(.scores.score)\n"' "$TEMP_DIR/top_candidates.json")

~/.claude/scripts/parallel_agent.py --json --full-output --timeout 600 \
    --cursor-model flash --claude-model sonnet \
    "You are an issue prioritization analyst. Score these open issues for a software project.

${PROJECT_CONTEXT:+## Project Context
$PROJECT_CONTEXT
}
## Scoring Dimensions (1-5 each)

- **Impact**: 5=blocks core functionality/data loss, 4=major user-facing, 3=reliability/DX, 2=nice-to-have, 1=cosmetic
- **Urgency**: 5=production problems, 4=blocks other work, 3=this sprint, 2=can wait, 1=backlog
- **Readiness**: 5=has implementation plan, 4=clear requirements, 3=needs design, 2=needs exploration, 1=vague
- **Risk**: 1=isolated/safe, 2=one service, 3=cross-service, 4=architectural, 5=critical path

**Formula**: (Impact × 3) + (Urgency × 2) + (Readiness × 2) - Risk

## Candidates

$CANDIDATES

## Instructions

For each issue return a JSON array:
[{\"number\": N, \"impact\": N, \"urgency\": N, \"readiness\": N, \"risk\": N, \"score\": N, \"type\": \"...\", \"rationale\": \"...\", \"services\": [\"...\"], \"dependencies\": \"...\"}]

Score objectively. Prefer bugs over features in ties. Consider which issues unblock others." \
    > "$TEMP_DIR/agent_scores.json"
```

Parse agent outputs and merge with heuristic scores:

```python
#!/usr/bin/env python3
"""Merge agent-refined scores with heuristic scores."""
import json
import sys

with open(sys.argv[1]) as f:
    candidates = json.load(f)

# Try to parse agent scores from JSON output
agent_data = {}
try:
    with open(sys.argv[2]) as f:
        agent_output = json.load(f)

    # Try each agent's output for parseable JSON
    for agent_name in ["claude", "gemini", "cursor"]:
        agent = agent_output.get("agents", {}).get(agent_name, {})
        if agent.get("status") != "complete":
            continue
        output = agent.get("output", "")
        # Find JSON array in output
        import re
        match = re.search(r'\[[\s\S]*?\]', output)
        if match:
            try:
                scores = json.loads(match.group())
                for s in scores:
                    num = str(s.get("number", ""))
                    if num not in agent_data:
                        agent_data[num] = []
                    agent_data[num].append(s)
            except json.JSONDecodeError as e:
                print(f"Skipping unparseable agent JSON array: {e}", file=sys.stderr)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Skipping agent data due to read error: {e}", file=sys.stderr)

# Merge: average agent scores if available, otherwise keep heuristic
for candidate in candidates:
    num = str(candidate["number"])
    if num in agent_data:
        agent_scores = agent_data[num]
        # Average across agents
        for dim in ["impact", "urgency", "readiness", "risk"]:
            vals = [s[dim] for s in agent_scores if dim in s]
            if vals:
                candidate["scores"][dim] = round(sum(vals) / len(vals))

        # Recalculate score with averaged dimensions
        s = candidate["scores"]
        s["score"] = (s["impact"] * 3) + (s["urgency"] * 2) + (s["readiness"] * 2) - s["risk"]

        # Merge metadata from first agent response
        first = agent_scores[0]
        candidate["scores"]["type"] = first.get("type", candidate["scores"].get("type", "feature"))
        candidate["scores"]["rationale"] = first.get("rationale", "")
        candidate["scores"]["services"] = first.get("services", [])
        candidate["scores"]["dependencies"] = first.get("dependencies", "None")
        candidate["agent_refined"] = True
    else:
        candidate["agent_refined"] = False

# Re-sort
def sort_key(issue):
    s = issue["scores"]
    type_priority = 0 if s["type"] == "bug" else 1
    has_plan = 0 if "planned" in {l.lower() for l in issue.get("labels", [])} else 1
    created = issue.get("created_at", "9999")
    return (-s["score"], type_priority, has_plan, created)

candidates.sort(key=sort_key)

print(json.dumps(candidates, indent=2))
```

Save final ranked candidates to `$TEMP_DIR/final_ranked.json`.

### Step 6: Codebase Context Validation (Optional)

For each top candidate, briefly check the codebase to validate references:

```bash
# For each top candidate, check if referenced files/services exist
jq -c ".[:$TOP_N]" "$TEMP_DIR/final_ranked.json" | jq -c '.[]' | while read -r issue; do
    body=$(echo "$issue" | jq -r '.body // ""')
    number=$(echo "$issue" | jq -r '.number')

    # Extract file paths from issue body
    file_refs=$(echo "$body" | grep -oE '`[^`]+\.[a-z]+`' | tr -d '`' | head -10)

    stale_refs=""
    if [[ -n "$file_refs" ]]; then
        while IFS= read -r ref; do
            # Check if file exists in repo (relative to repo root)
            if [[ ! -f "$ref" ]]; then
                stale_refs="${stale_refs}${ref}, "
            fi
        done <<< "$file_refs"
    fi

    if [[ -n "$stale_refs" ]]; then
        echo "STALE_WARNING: #$number references missing files: ${stale_refs%, }"
    fi
done > "$TEMP_DIR/stale_warnings.txt" 2>/dev/null
```

### Step 7: Generate Report

Produce the final prioritization report in markdown format.

```bash
# Variables set from earlier steps:
# ISSUE_COUNT — total issues analyzed (after filtering)
# TOP_N — number of top issues to show (default: 5)
# PLATFORM — detected platform

TOTAL_COUNT=$(jq 'length' "$TEMP_DIR/issues.json")
REPORT_DATE=$(date -u +"%Y-%m-%d %H:%M UTC")

LABEL_NOTE=""
if [[ "$FILTER_ALL" == true ]]; then
    LABEL_NOTE="all open issues"
else
    LABEL_NOTE="label: \`$FILTER_LABEL\`"
fi

cat << REPORT_HEADER
# Issue Prioritization Report

**Generated**: $REPORT_DATE
**Platform**: $PLATFORM
**Filter**: $LABEL_NOTE
**Open Issues Analyzed**: $TOTAL_COUNT
REPORT_HEADER

echo ""
echo "## Top $TOP_N Recommended Issues"
echo ""

# Top N issues
jq -c ".[:$TOP_N]" "$TEMP_DIR/final_ranked.json" | jq -c '.[]' | {
    rank=0
    while read -r issue; do
        rank=$((rank + 1))
        number=$(echo "$issue" | jq -r '.number')
        title=$(echo "$issue" | jq -r '.title')
        type=$(echo "$issue" | jq -r '.scores.type')
        score=$(echo "$issue" | jq -r '.scores.score')
        impact=$(echo "$issue" | jq -r '.scores.impact')
        urgency=$(echo "$issue" | jq -r '.scores.urgency')
        readiness=$(echo "$issue" | jq -r '.scores.readiness')
        risk=$(echo "$issue" | jq -r '.scores.risk')
        rationale=$(echo "$issue" | jq -r '.scores.rationale // "Scored by heuristic analysis"')
        services=$(echo "$issue" | jq -r '.scores.services // [] | join(", ")')
        deps=$(echo "$issue" | jq -r '.scores.dependencies // "None"')
        has_plan=$(echo "$issue" | jq -r 'if (.labels | map(ascii_downcase) | index("planned")) then "Yes" else "No" end')

        # Check for stale warnings
        stale_note=""
        if grep -q "#$number" "$TEMP_DIR/stale_warnings.txt" 2>/dev/null; then
            stale_note=" (**Potentially stale** — references missing files)"
        fi

        echo "### $rank. #$number — $title"
        echo "- **Type**: $type | **Score**: $score"
        echo "- **Impact**: $impact | **Urgency**: $urgency | **Readiness**: $readiness | **Risk**: $risk"
        [[ -n "$services" ]] && echo "- **Services**: $services"
        echo "- **Rationale**: $rationale${stale_note}"
        echo "- **Has Plan**: $has_plan"
        [[ "$deps" != "None" && "$deps" != "null" ]] && echo "- **Dependencies**: $deps"
        echo ""
    done
}

echo "## Scoring Summary"
echo ""
echo "| Rank | Issue | Type | Impact | Urgency | Readiness | Risk | Score |"
echo "|------|-------|------|--------|---------|-----------|------|-------|"

jq -r ".[:$TOP_N] | to_entries[] |
\"| \(.key + 1) | #\(.value.number) | \(.value.scores.type) | \(.value.scores.impact) | \(.value.scores.urgency) | \(.value.scores.readiness) | \(.value.scores.risk) | \(.value.scores.score) |\"" \
    "$TEMP_DIR/final_ranked.json"

echo ""
echo "## Honorable Mentions"
echo ""

# Next 2-3 after top N
MENTION_START=$TOP_N
MENTION_END=$((TOP_N + 3))
jq -r ".[$MENTION_START:$MENTION_END][] |
\"- **#\(.number)** — \(.title) (Score: \(.scores.score), Type: \(.scores.type))\"" \
    "$TEMP_DIR/final_ranked.json" 2>/dev/null || echo "No additional candidates."

echo ""
echo "## Observations"
echo ""

# Auto-generate observations from the data
jq -r '
def count_type(t): [.[] | select(.scores.type == t)] | length;
def avg_score: if length == 0 then 0 else ([.[].scores.score] | add / length | . * 10 | floor / 10) end;

"- **Total open issues**: \(length)
- **Type distribution**: \(count_type("bug")) bugs, \(count_type("feature")) features, \(count_type("enhancement")) enhancements, \(count_type("tech-debt")) tech-debt, \(count_type("infra")) infra, \(count_type("test")) test, \(count_type("docs")) docs
- **Average score**: \(avg_score)
- **High-impact issues (4-5)**: \([.[] | select(.scores.impact >= 4)] | length)
- **Low-readiness issues (1-2)**: \([.[] | select(.scores.readiness <= 2)] | length) — may need requirements gathering"
' "$TEMP_DIR/scored_issues.json"

# Check for stale file references
if [[ -s "$TEMP_DIR/stale_warnings.txt" ]]; then
    echo ""
    echo "### Stale File References"
    echo ""
    cat "$TEMP_DIR/stale_warnings.txt" | while read -r line; do
        echo "- $line"
    done
fi
```

### Step 8: STOP

Report the prioritization report to the user. **Do not begin implementing any issues.**

---
