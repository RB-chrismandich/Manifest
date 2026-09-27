---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
We mirror a daily grant-recipient roster that's re-published in full each morning
(no diffs, no version field) using a delete-then-insert loader:

```python
def load_roster(conn, rows: list[dict]):
    with conn:
        conn.execute("DELETE FROM grant_recipients")
        for r in rows:
            conn.execute(
                "INSERT INTO grant_recipients (org, amount, program) VALUES (?, ?, ?)",
                (r["org"], r["amount"], r["program"]),
            )
```

Twice now, the upstream API had a maintenance window and returned an empty list.
Both times our entire `grant_recipients` table got wiped for the day since the
loader ran with `rows = []`. How do we harden this so a transient empty response
doesn't destroy good data?
