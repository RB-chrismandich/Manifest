---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Prioritize our `future` backlog and give me the top 3:

```json
[
 {"number":11,"title":"Data loss: exports truncate at 10k rows","labels":["future","bug"],"body":"Repro: export 12k rows -> file has 10000. Expected all rows. Blocks #14, #15.","updated":"2026-09-20"},
 {"number":12,"title":"Dark mode","labels":["future","enhancement"],"body":"Would be nice.","updated":"2026-04-01"},
 {"number":13,"title":"Refactor legacy/reporting.py","labels":["future"],"body":"legacy/reporting.py is messy. (note: file was deleted in #300)","updated":"2025-12-10"},
 {"number":14,"title":"Add export progress bar","labels":["future"],"body":"Depends on #11.","updated":"2026-09-01"},
 {"number":16,"title":"Upgrade CI runners to Ubuntu 26.04","labels":["infra"],"body":"Current runners EOL 2026-10-15. Clear steps in runbook.","updated":"2026-09-22"}
]
```

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
