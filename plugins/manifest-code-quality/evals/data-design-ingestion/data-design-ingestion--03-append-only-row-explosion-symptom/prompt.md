---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our `filings` table has ballooned to 40x the row count we expected. The ingestion
is append-only with a deterministic dedup id and `INSERT OR IGNORE`:

```python
def dedup_id(record: dict) -> str:
    key = f"{record['filer']}:{record['period']}:{record['amount']:.2f}"
    return hashlib.sha1(key.encode()).hexdigest()
```

Turns out the upstream disclosure feed re-publishes each filer's full filing
history every week — the same filing period shows up again next week, sometimes
with a slightly corrected `amount` after the filer fixes a typo. Since `amount` is
part of the dedup key, the corrected version hashes to a different id and gets
inserted as a "new" row, forever.

What's actually wrong with how we designed this ingestion, and how do we fix it?
