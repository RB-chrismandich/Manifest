---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
The unit test for `_attach_backlog_ratio` passes and I know the math is right, but
I want a second pair of eyes: is `backlog_ratio` actually populated when
`run_pipeline` runs for real?

`pipeline.py`:
```python
from dataclasses import dataclass, replace
from typing import Optional

@dataclass
class RiskSnapshot:
    ticker: str
    debt: float
    backlog: float
    backlog_ratio: Optional[float] = None

def fetch_and_build(ticker: str) -> RiskSnapshot:
    debt, backlog = _fetch_financials(ticker)
    return RiskSnapshot(ticker=ticker, debt=debt, backlog=backlog)

def _attach_backlog_ratio(snap: RiskSnapshot) -> RiskSnapshot:
    ratio = snap.backlog / snap.debt if snap.debt else 0.0
    return replace(snap, backlog_ratio=ratio)

def run_pipeline(tickers: list[str]) -> list[RiskSnapshot]:
    return [fetch_and_build(t) for t in tickers]
```

`test_pipeline.py`:
```python
def test_backlog_ratio_attached():
    snap = RiskSnapshot(ticker="ACME", debt=100.0, backlog=50.0)
    enriched = _attach_backlog_ratio(snap)
    assert enriched.backlog_ratio == 0.5
```
