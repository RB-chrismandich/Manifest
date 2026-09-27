---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our webhook receiver for the payments provider is throwing 429 rate-limit errors
under load and dropping events. The parsing logic itself is already validated and
fine — I just need to know how to add retry with exponential backoff around the
outbound call so we stop losing events.
