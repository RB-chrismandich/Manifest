---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
About to open the PR for this daily price-anomaly flagger. Here's the code and a
real window of closing prices captured from our vendor feed (which paginates in
overlapping windows to be safe against gaps) — sanity check it before I request
review.

`price_zscore.py`:
```python
import statistics

def parse_price(raw: str) -> float:
    return float(raw)

def flag_anomalies(prices: list[dict]) -> list[dict]:
    values = [parse_price(p["close"]) for p in prices]
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values)
    flagged = []
    for p, v in zip(prices, values):
        z = (v - mean) / stdev
        flagged.append({**p, "z_score": z, "anomaly": abs(z) > 2})
    return flagged
```

Real captured window:
```python
prices = [
    {"date": "2026-03-01", "close": "9.98"},
    {"date": "2026-03-02", "close": "10.02"},
    {"date": "2026-03-03", "close": "10.01"},
    {"date": "2026-03-03", "close": "10.01"},
    {"date": "2026-03-04", "close": "9.99"},
]
```
(The two 2026-03-03 rows are identical — the vendor's overlapping pagination
windows returned that day twice.)
