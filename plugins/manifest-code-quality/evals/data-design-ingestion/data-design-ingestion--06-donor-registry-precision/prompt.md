---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Here's our ingestion for completed court judgments (each judgment is final and
public record the moment it's entered — the court never edits or retracts one,
and each carries a `judgment_id` the court assigns once and never reuses).
We re-fetch a trailing 14-day window every run to cover clerical filing delays.
Does this design need any changes before I ship it?

```python
import hashlib

SCHEMA = """
CREATE TABLE IF NOT EXISTS judgments (
    id          TEXT PRIMARY KEY,
    court       TEXT NOT NULL,
    judgment_id TEXT NOT NULL,
    case_number TEXT NOT NULL,
    amount      NUMERIC NOT NULL,
    entered_at  TEXT NOT NULL
)
"""


def dedup_id(j: dict) -> str:
    # court + court-assigned judgment_id is the judgment's permanent identity.
    key = f"{j['court']}:{j['judgment_id']}"
    return hashlib.sha1(key.encode()).hexdigest()


def load_judgments(conn, judgments: list[dict]) -> None:
    with conn:
        conn.execute(SCHEMA)
        for j in judgments:
            conn.execute(
                "INSERT OR IGNORE INTO judgments "
                "(id, court, judgment_id, case_number, amount, entered_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (dedup_id(j), j["court"], j["judgment_id"], j["case_number"],
                 j["amount"], j["entered_at"]),
            )
```
