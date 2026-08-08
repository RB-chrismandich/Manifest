---
name: metrics-report
description: Analyze bundle-owned agent result artifacts for completion, consensus, failure, latency, and provider trends without mutating runtime state.
---

# Metrics Report

Read JSON result artifacts below
`$XDG_STATE_HOME/manifest/agent-outputs/`. Produce totals, completion and failure
rates, consensus distribution, duration summaries, provider/model usage, and
the time window covered.

Ignore malformed files only with an explicit warning naming each file. If no
artifacts exist, report `DEGRADED` and suggest `[[skill:parallel-agent]]` to
produce structured results. This skill is read-only.
