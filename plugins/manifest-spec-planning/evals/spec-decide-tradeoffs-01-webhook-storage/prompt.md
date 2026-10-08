---
max_turns: 18
timeout_seconds: 300
allowed_tools: [Skill, Read, Write]
runs: 3
---
We are choosing a storage model for webhook delivery attempts. Read `specs/webhook/design.md`, compare both options across replayability/auditability, read cost, and operational complexity, recommend one, and record the chosen decision plus its accepted trade-off in the document's Decisions section. Keep the two options on equal footing; do not invent constraints. The current draft leans toward the mutable summary row, but that lean is not a requirement.
