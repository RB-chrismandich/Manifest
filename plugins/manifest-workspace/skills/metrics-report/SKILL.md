---
name: metrics-report
description: "Use when the user wants agent-efficiency metrics — completion rates, error patterns, consensus scores, model usage — visualized from ~/.claude/.agent_outputs/ logs as markdown dashboard tables (\"agent dashboard\", \"metrics report\")."
---

# Dashboard Skill

Generate a metrics dashboard from parallel agent output logs. Aggregates data
from `~/.claude/.agent_outputs/` to show trends, consensus patterns, and model
usage over time.

## Arguments

- `$ARGUMENTS` -- One of:
  - (empty) -- Show full dashboard for last 30 days
  - `today` -- Show today's metrics only
  - `week` -- Show last 7 days
  - `month` -- Show last 30 days (default)
  - `all` -- Show all available data

---

## Phase 1: Data Collection

Scan `~/.claude/.agent_outputs/` for result files:

| File Pattern | Data Source |
|-------------|-------------|
| `results_*.json` | JSON output from `--json` runs |
| `summary_*.md` | Markdown summaries |
| `cursor_*.txt` | Raw Cursor agent output |
| `gemini_*.txt` | Raw Gemini agent output |
| `claude_*.txt` | Raw Claude agent output |

Parse timestamps from filenames (`YYYYMMDD_HHMMSS`) to filter by date range.

If no result files exist, report:

```text
No agent output data found in ~/.claude/.agent_outputs/
Run manifest parallel-agent with --json to generate trackable data.
```

---

## Phase 2: Metrics Extraction

From each `results_*.json`, extract:

| Metric | JSON Path | Type |
|--------|-----------|------|
| Mode | `.mode` | categorical |
| Agent status | `.agents.{name}.status` | categorical |
| Agent model | `.agents.{name}.model` | categorical |
| Credit fallback | `.agents.{name}.credit_fallback` | boolean |
| Consensus score | `.cross_verification.consensus_score` | numeric |
| Confidence level | `.cross_verification.confidence` | categorical |
| Agent count | `.cross_verification.agent_count` | numeric |
| Validation pass | `.agents.{name}.validated` | boolean |

---

## Phase 3: Aggregation

Compute the following aggregate metrics:

### Task Metrics

| Metric | Computation |
|--------|-------------|
| Total runs | Count of result files in range |
| Runs per day | Total / days in range |
| Mode distribution | Count by mode (review, analyze, prompt) |

### Agent Metrics

| Metric | Computation |
|--------|-------------|
| Availability rate | `complete / (complete + failed + missing)` per agent |
| Failure rate | `failed / total` per agent |
| Credit fallback rate | `credit_fallback=true / total` per agent |
| Model distribution | Count by model tier per agent |

### Consensus Metrics

| Metric | Computation |
|--------|-------------|
| Mean consensus | Average consensus score |
| High confidence % | Runs with confidence=high / total |
| Medium confidence % | Runs with confidence=medium / total |
| Low confidence % | Runs with confidence=low / total |

### Error Patterns

Scan agent output files for common error patterns:

| Pattern | Regex |
|---------|-------|
| Timeout | `timeout\|timed out\|exceeded` |
| Auth failure | `auth\|unauthorized\|401\|403` |
| Rate limit | `rate.limit\|quota\|429\|too many requests` |
| Not found | `not found\|404\|no such` |
| Credit exhaustion | `credit\|billing\|exceeded.*limit` |

---

## Phase 4: Output Dashboard

```markdown
## Agent Dashboard

**Period**: {start-date} to {end-date}
**Total runs**: {count}
**Avg runs/day**: {avg}

### Task Distribution

| Mode | Count | % |
|------|-------|---|
| review | 15 | 50% |
| analyze | 8 | 27% |
| prompt | 7 | 23% |

### Agent Availability

| Agent | Available | Failed | Missing | Availability |
|-------|-----------|--------|---------|-------------|
| Cursor | 25 | 3 | 2 | 83% |
| Gemini | 28 | 1 | 1 | 93% |
| Claude | 27 | 2 | 1 | 90% |

### Model Usage

| Agent | Model | Count | Fallbacks |
|-------|-------|-------|-----------|
| Cursor | auto | 18 | 0 |
| Cursor | gpt-5.1-codex | 8 | 2 |
| Claude | sonnet | 20 | 0 |
| Claude | haiku | 5 | 3 |
| Claude | opus | 5 | 0 |

### Consensus Trends

| Metric | Value |
|--------|-------|
| Mean consensus score | 78% |
| High confidence runs | 60% |
| Medium confidence runs | 30% |
| Low confidence runs | 10% |

### Error Patterns

| Pattern | Occurrences | Most Affected Agent |
|---------|-------------|-------------------|
| Timeout | 3 | Cursor |
| Rate limit | 2 | Gemini |
| Credit exhaustion | 1 | Claude |

### Recommendations

Based on the data:
- {actionable insight 1}
- {actionable insight 2}
- {actionable insight 3}
```

Generate 2-3 actionable recommendations based on the data. Examples:

- "Cursor failure rate is 17% -- consider using `--no-cursor` or checking installation"
- "Credit fallback triggered 3 times for Claude opus -- consider defaulting to sonnet"
- "Mean consensus is 65% (medium) -- review synthesis quality for disagreements"

---

## Safety Checks

- Read-only analysis -- never modify or delete log files
- Handle malformed JSON gracefully (skip and note)
- Report if `.agent_outputs/` directory is missing or empty
- Cap file scanning to 1000 most recent files
