---
name: issue-prioritize
description: Fetch open issues from GitHub, GitLab, Linear, or Jira, score them by impact/urgency/readiness/risk, and recommend the top issues to address next. Analysis-only — no mutations.
---

# Issue Prioritization Skill

Fetch open issues, score them using a weighted formula, and produce a ranked prioritization
report. Works with GitHub, GitLab, Linear, and Jira (agent-context only, via MCP).
**Read-only** — never modifies issues or files.

## Purpose

1. Fetch open issues from the detected (or specified) provider
2. Filter to issues with the `future` label by default (use `--all` for all open issues)
3. Score each issue on Impact, Urgency, Readiness, and Risk (1–5 each)
4. Rank by weighted formula with tiebreakers
5. Optionally validate top candidates against the codebase
6. Present a formatted prioritization report

## Arguments

```bash
/issue-prioritize [--repo OWNER/REPO] [--provider github|gitlab|linear|jira]
                  [--team TEAM] [--limit N] [--top N]
                  [--label LABEL] [--all] [--project-context FILE]
```

| Argument | Description | Default |
|----------|-------------|---------|
| `--repo OWNER/REPO` | Target repository (GitHub/GitLab only) | current repo |
| `--provider github\|gitlab\|linear\|jira` | Force provider (default: auto-detect via `tracker_ops.sh`) | auto-detect |
| `--team TEAM` | Linear team key filter | all teams |
| `--limit N` | Max issues to fetch | 100 |
| `--top N` | How many top issues to report | 5 |
| `--label LABEL` | Only include issues with this label | `future` |
| `--all` | Include all open issues (ignore label filter) | false |
| `--project-context FILE` | Markdown/YAML file with project-specific context | none |

## Prerequisites

1. **Provider CLI/access configured** — at least one of:
   - `gh` (GitHub CLI) — for GitHub repos
   - `glab` (GitLab CLI) — for GitLab repos
   - Linear MCP or API key — for Linear projects
   - Atlassian MCP — for Jira projects (agent-context only; see note below)
2. **Scripts available**:
   - `~/.claude/scripts/tracker_ops.sh` — provider-agnostic tracker operations (detection + verbs)
   - `~/.claude/scripts/linear_ops.sh` — Linear API wrapper (invoked internally by `tracker_ops.sh` for the `linear` provider)
3. **Tools**: `jq`, `python3`
4. Jira is agent-context only (MCP); when `PROVIDER=jira`, fetch via the Atlassian MCP tools named
   in `tracker_providers.yml` instead of `tracker_ops.sh` (which exits 3).

## Critical Rules

1. **Do not implement anything.** This command is analysis-only.
2. **Do not modify any files** in the repository.
3. **Do not mutate issues** (no labels, no comments, no state changes).
4. **Score objectively.** Do not inflate scores based on how interesting an issue is.
5. **Consider dependencies.** An issue that unblocks others is more valuable than isolated work.
6. **Flag stale issues.** If an issue references code/files that no longer exist, note it.

---

## Workflow

The full step-by-step workflow — including the exact scripts to run at each step — lives in
[references/workflow.md](references/workflow.md). **Read that file and execute each step in order in one shell
session** (later steps consume env vars and intermediate files set by earlier ones). Steps:

1. Step 1: Resolve Provider
2. Step 2: Fetch Open Issues
3. Step 3: Normalize
4. Step 4: Heuristic Pre-Scoring
5. Step 5: Agent-Refined Scoring for Top Candidates
6. Step 6: Codebase Context Validation (Optional)
7. Step 7: Generate Report
8. Step 8: STOP

## Parallel Agent Usage

Parallel agents are used sparingly — only for the top candidates:

| Step | Agents | Purpose |
|------|--------|---------|
| Step 5 | flash/sonnet | Refine scoring for top 5-7 candidates |

**Model selection** (balanced — not security-critical):

| Agent | Model | Reason |
|-------|-------|--------|
| Cursor | flash | Good reasoning for scoring |
| Claude | sonnet | Balanced analysis |
| Gemini | flash | Diverse perspective |

If agents fail or time out, the heuristic scores from Step 4 are used as-is.

## Scoring Formula

```text
Priority Score = (Impact × 3) + (Urgency × 2) + (Readiness × 2) - Risk
```

**Range**: 4 (all 1s) to 34 (all 5s, risk 1)

### Dimension Definitions

**Impact** (1–5):

- 5: Blocks core functionality or causes data loss
- 4: Affects user-facing features significantly
- 3: Improves reliability, performance, or developer experience
- 2: Nice-to-have improvement
- 1: Cosmetic or minor

**Urgency** (1–5):

- 5: Actively causing problems in production
- 4: Will cause problems soon or blocks other work
- 3: Should be done this sprint
- 2: Can wait but shouldn't be forgotten
- 1: Backlog — do when convenient

**Readiness** (1–5):

- 5: Well-defined, has an implementation plan, can start immediately
- 4: Clear requirements, needs minor investigation
- 3: Requirements known but needs design work
- 2: Needs significant exploration or discussion
- 1: Vague, needs requirements gathering

**Risk** (1–5, lower is better for priority):

- 1: Isolated change, low risk of breakage
- 2: Touches one service, moderate testing needed
- 3: Cross-service change, careful coordination needed
- 4: Architectural change, significant testing needed
- 5: High-risk change to critical path (data integrity, auth, payments)

### Tiebreaker Rules

When scores are equal, prefer:

1. Bugs over features
2. Issues that unblock other issues
3. Issues with `planned` label (have implementation plans)
4. Older issues over newer ones

## Example Usage

```bash
# Prioritize issues labeled 'future' (default)
/issue-prioritize

# Prioritize ALL open issues (ignore label filter)
/issue-prioritize --all

# Filter by a different label instead of 'future'
/issue-prioritize --label "enhancement"

# Prioritize a specific GitHub repo
/issue-prioritize --repo ReefBytes/cookedbooks --limit 200

# Prioritize with project context
/issue-prioritize --project-context docs/PROJECT_CONTEXT.md

# Prioritize Linear issues for a specific team
/issue-prioritize --provider linear --team ENG --top 10

# GitLab repo prioritization
/issue-prioritize --provider gitlab --repo mygroup/myproject

# Prioritize Jira issues (agent-context only, fetched via the Atlassian MCP)
/issue-prioritize --provider jira --top 10
```

## Output Format

The report is printed to the console in markdown format. No files are created or modified
in the repository. The report includes:

1. **Top N Recommended Issues** — detailed cards with scores and rationale
2. **Scoring Summary** — compact table for quick comparison
3. **Honorable Mentions** — 2-3 near-misses with brief reasoning
4. **Observations** — patterns and statistics across the full issue set

## Error Handling

- **No issues found**: Report "No open issues found" and exit cleanly
- **Provider CLI/access missing**: `tracker_ops.sh` errors with install/config instructions
- **`PROVIDER=jira` in shell context**: `tracker_ops.sh` exits 3 by design — fetch via the
  Atlassian MCP instead (see Step 2 Jira note), not an error to report to the user
- **Agent timeout**: Fall back to heuristic-only scores (Step 4)
- **Agent parse failure**: Fall back to heuristic-only scores (Step 4)
- **Empty body issues**: Score with defaults (readiness=2, risk=2)

## Sub-agent dispatch

When ≥10 open issues need scoring, dispatch one sub-agent per issue batch to score them, then merge into one ranking;
below that, score inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `[[skill:parallel-agent]]` / inline
on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.
