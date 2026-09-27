---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I just finished the parser for our nightly donor-contribution import. Unit tests
(built on hand-written fixtures) are all green. Before I open the PR, run a live-data
validation pass using this real export sample pulled from prod and tell me what
breaks.

`parse_contributions.py`:
```python
import sqlite3

def parse_amount(raw):
    return float(raw)

def dedup_key(record):
    return f"{record['last_name']}:{record['date']}"

def load_contributions(conn: sqlite3.Connection, records: list[dict]):
    seen = {}
    for r in records:
        amount = parse_amount(r["amount"])
        match = r.get("employer_match")
        match_amount = float(match) if match else None
        key = dedup_key(r)
        seen[key] = {
            "last_name": r["last_name"],
            "date": r["date"],
            "amount": amount,
            "employer_match": match_amount,
        }
    with conn:
        for key, rec in seen.items():
            conn.execute(
                "INSERT OR IGNORE INTO contributions "
                "(dedup_key, last_name, date, amount, employer_match) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, rec["last_name"], rec["date"], rec["amount"], rec["employer_match"]),
            )
```

Real sample pulled from prod (`live_sample.json`):
```json
[
  {"last_name": "Smith", "date": "2026-03-01", "amount": "1,000.00", "employer_match": 250},
  {"last_name": "Smith", "date": "2026-03-01", "amount": "750", "employer_match": 0},
  {"last_name": "Nguyen", "date": "2026-03-02", "amount": "2,340.50", "employer_match": null},
  {"last_name": "Alvarez", "date": "2026-03-02", "amount": "500", "employer_match": 0}
]
```
