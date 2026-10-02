---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
All 40 unit tests pass for the lobbying-expenditure aggregator. Before I mark the
ticket done, here's the code plus a small real response I captured from the state
portal's staging endpoint — can you check it against this before I close it out?

`aggregate_expenditures.py`:
```python
def parse_amount(raw: str) -> float:
    cleaned = raw.replace("$", "").replace(",", "")
    return float(cleaned)

def build_key(record: dict) -> str:
    return f"{record['bill_id']}:{record['quarter']}"

def aggregate(records: list[dict]) -> dict:
    totals = {}
    for r in records:
        key = build_key(r)
        totals[key] = {
            "bill_id": r["bill_id"],
            "quarter": r["quarter"],
            "amount": parse_amount(r["amount"]),
            "lobbyist_count": r.get("lobbyist_count"),
        }
    return totals

def summarize(totals: dict) -> list[str]:
    lines = []
    for rec in totals.values():
        if rec["lobbyist_count"]:
            lines.append(f"{rec['bill_id']} {rec['quarter']}: ${rec['amount']:.2f} across {rec['lobbyist_count']} lobbyists")
        else:
            lines.append(f"{rec['bill_id']} {rec['quarter']}: ${rec['amount']:.2f} (lobbyist count unknown)")
    return lines
```

Real staging response:
```json
[
  {"bill_id": "HB204", "quarter": "2026Q1", "amount": "$12,500.00", "lobbyist_count": 3},
  {"bill_id": "HB204", "quarter": "2026Q1", "amount": "$4,800.00", "lobbyist_count": 0},
  {"bill_id": "SB88", "quarter": "2026Q1", "amount": "$900", "lobbyist_count": 1}
]
```
(The two HB204 rows are two different registered lobbying firms both reporting
expenditures on the same bill in the same quarter — that's normal for this feed.)
