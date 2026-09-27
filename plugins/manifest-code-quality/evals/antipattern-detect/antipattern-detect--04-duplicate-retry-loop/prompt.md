---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
We ran a quick duplicate-code scan and it flagged the same helper reimplemented in three places:

```
$ jscpd src/
Clone found (javascript):
 - src/utils/retry.js [10:1 - 22:1]
 - src/jobs/processPayment.js [45:1 - 57:1]
 - src/jobs/syncInventory.js [88:1 - 100:1]
Duplicated lines: 36 (2.1%)
```

Each copy is basically the same exponential-backoff retry loop, hand-copied instead of imported. Should we track this?

Just give me the analysis and the knowledge-base entry you would record (category, mechanism, detection cue, prevention rule). Don't try to save it anywhere — the knowledge base isn't available in this environment.
