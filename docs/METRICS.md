# Development Metrics Dashboard

> Template for tracking agent performance, consensus quality, error patterns,
> and learning capture across the Manifest orchestration framework.

**Last Updated**: 2026-02-11
**Managed by**: `metrics-report` skill
**Data source**: `.claude/.agent_outputs/` logs

---

## Overview

This dashboard provides visibility into the operational health of the parallel
agent orchestration system. All tables start empty (headers only) and are
populated automatically by the `/metrics-report` skill, which reads from
`.agent_outputs/` logs and `~/.claude/config/` data files.

---

## Agent Efficiency

Performance metrics per agent across all orchestrated tasks.

| Agent | Tasks Run | Success Rate | Avg Duration | Credit Usage |
|-------|-----------|--------------|--------------|--------------|
| | | | | |

---

## Consensus Scores

Distribution of cross-verification consensus scores across all orchestrated runs.

| Range | Label | Count | Percentage |
|-------|-------|-------|------------|
| >= 80% | High confidence | | |
| 50-79% | Medium confidence | | |
| < 50% | Low confidence | | |

**Interpretation**:

- **High (>= 80%)**: Agents agree on key findings; recommendations are auto-approved.
- **Medium (50-79%)**: Partial agreement; disagreements are highlighted for review.
- **Low (< 50%)**: Significant disagreement; escalated for human decision.

---

## Common Error Patterns

Recurring errors observed across agent runs and CI pipelines.

| Pattern | Frequency | Last Seen | Resolution |
|---------|-----------|-----------|------------|
| | | | |

---

## Learning Capture Frequency

Volume of knowledge base entries by category over time.

| Category | Total Entries | Last 7 Days | Last 30 Days |
|----------|---------------|-------------|--------------|
| Patterns | | | |
| Antipatterns | | | |
| Tool Discoveries | | | |
| Configuration Insights | | | |

---

## Model Usage Distribution

Breakdown of model tiers selected for orchestrated tasks.

| Tier | Cursor Model | Claude Model | Gemini Model | Codex Model | Antigravity Model | Usage Count |
|------|--------------|--------------|--------------|-------------|-------------------|-------------|
| mini / haiku | cursor-grok-4.5-low | claude-haiku-4-5 | -- | gpt-5.4-mini | gemini-3.6-flash-low | |
| flash / sonnet | cursor-grok-4.5-medium | claude-sonnet-5 | gemini-3-flash-preview | gpt-5.4 | gemini-3.6-flash-high | |
| advanced / opus / pro | cursor-grok-4.5-high | claude-opus-5 | gemini-3-pro-preview | gpt-5.5 | claude-opus-4-6-thinking | |
| fable (security) | -- | claude-fable-5 | -- | -- | -- | |

---

## How to Generate

Run the dashboard skill to auto-populate these tables from live data:

```bash
# In Claude Code
/metrics-report

# The skill reads from:
#   ~/.claude/.agent_outputs/results_*.json   -- agent run logs
#   ~/.claude/config/knowledge_base.yml       -- learning entries
#   ~/.claude/config/command_config.yml        -- model/threshold config
```

Tables are regenerated on each run. Previous values are overwritten with current data.

---

## References

- **Agent output logs**: `~/.claude/.agent_outputs/`
- **Knowledge base**: [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md)
- **Knowledge base config**: [`configs/claude/config/knowledge_base.yml`](../configs/claude/config/knowledge_base.yml)
- **Validation criteria**: [`configs/claude/config/validation_criteria.yml`](../configs/claude/config/validation_criteria.yml)
- **Command config**: [`configs/claude/config/command_config.yml`](../configs/claude/config/command_config.yml)
- **Dashboard skill**: [`configs/claude/skills/metrics-report/SKILL.md`](../configs/claude/skills/metrics-report/SKILL.md)
