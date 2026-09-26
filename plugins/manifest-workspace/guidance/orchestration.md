---
id: workspace-orchestration
---

# Orchestration Guidance

Delegate bounded independent work only when it materially reduces latency or
adds an independent review lens. Keep one writer per file set, give every agent
explicit inputs and acceptance criteria, and integrate results against the same
tree revision.

For independent interactive review, define bounded units and use the current
host's native mechanism. OMP parents batch ready units with `task` and
coordinate with `hub`; Claude Code parents use only discovered native Agent
types and background collection. Follow the deployed host's shared dispatch
contract for child limits, the narrow delegate-runner exception, and
`DEGRADED` behavior.

Capture reusable findings through `manifest-workspace:learning-capture`. Capture failure
is advisory and never changes the primary task verdict.
