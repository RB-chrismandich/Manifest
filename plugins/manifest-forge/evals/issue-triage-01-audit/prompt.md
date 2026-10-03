---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Audit our issue backlog and clean it up (today 2026-09-26):

```json
[
 {"number":40,"title":"Login fails with SSO when email has +","labels":["bug"],"updated":"2026-09-10"},
 {"number":41,"title":"SSO login broken for plus-addressed emails","labels":["bug"],"updated":"2026-09-18"},
 {"number":42,"title":"Speed up scripts/old_sync.sh","labels":["planned"],"updated":"2025-08-01","body":"scripts/old_sync.sh is slow"},
 {"number":43,"title":"Crash in src/legacy/importer.py on empty CSV","labels":["bug"],"updated":"2025-10-02","body":"src/legacy/importer.py line 40"},
 {"number":44,"title":"Typo on pricing page","labels":["P0"],"updated":"2026-09-25"}
]
```
Repo facts: `scripts/old_sync.sh` was deleted; `src/legacy/importer.py` still exists.

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
