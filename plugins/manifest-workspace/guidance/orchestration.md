---
id: workspace-orchestration
---

# Orchestration Guidance

Delegate bounded independent work only when it materially reduces latency or
adds an independent review lens. Keep one writer per file set, give every agent
explicit inputs and acceptance criteria, and integrate results against the same
tree revision.

For independent interactive review, define bounded units and dispatch all ready
units in one OMP `task` call (at most 32 per wave). Children execute one unit
without redispatching; the parent validates returned evidence and uses `hub`
only to coordinate or wait. If task dispatch is unavailable, perform the review
inline and report `DEGRADED`; never fall back to a provider CLI.

Capture reusable findings through `manifest-workspace:learning-capture`. Capture failure
is advisory and never changes the primary task verdict.
