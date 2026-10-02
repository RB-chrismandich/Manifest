---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
All 3 parametrized unit tests for the independent-expenditure parser are green.
Before I merge, here's a real sample pulled from the FEC bulk data export — can
you check it before I open the PR?

`test_parse_expenditures.py`:
```python
import pytest
from parse_expenditures import parse_amount

@pytest.mark.parametrize("raw,expected", [
    ("1,000.00", 1000.0),
    ("250.50", 250.5),
    ("48,900.75", 48900.75),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected
```

`parse_expenditures.py`:
```python
import re

def parse_amount(raw: str) -> float:
    cleaned = re.sub(r"[,$]", "", raw)
    return float(cleaned)

def summarize(records: list[dict]) -> dict:
    total = 0.0
    for r in records:
        total += parse_amount(r["amount"])
    return {"count": len(records), "total": total}
```

Real sample pulled from the FEC bulk export (`live_sample.json`):
```json
[
  {"committee": "Citizens for Reform", "amount": "12,500.00"},
  {"committee": "Alliance PAC", "amount": "Over $1,000,000"},
  {"committee": "Neighbors United", "amount": "48,900.75"}
]
```
(The "Over $1,000,000" value is how the FEC export reports an independent
expenditure when the committee discloses a threshold instead of an exact final
figure at filing time — this shows up on real exports but never in our test
fixtures.)
