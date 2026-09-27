---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our state's lobbyist registration feed returns the FULL current list of ~4,000
active registrations every time we call it — it's not incremental. Past entries
also get corrected in place (address changes, employer changes) with no
"version" or "last modified" field to tell us what changed. I need to mirror this
into a local table for internal search.

What's the right way to load it so corrections show up and stale/deregistered
entries don't linger?
