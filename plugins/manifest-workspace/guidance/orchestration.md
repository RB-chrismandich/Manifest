---
id: workspace-orchestration
---

# Orchestration Guidance

Delegate bounded independent work only when it materially reduces latency or
adds an independent review lens. Keep one writer per file set, give every agent
explicit inputs and acceptance criteria, and integrate results against the same
tree revision.

For cross-provider review, invoke `[[skill:parallel-agent]]` with target files,
mode, validation flag, and timeout. Consume structured JSON when supported;
otherwise perform the review inline and report `DEGRADED`.

Capture reusable findings through `[[skill:learning-capture]]`. Capture failure
is advisory and never changes the primary task verdict.
