---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
I added `liquidity_score` to `PortfolioSnapshot` and wrote `compute_liquidity_score()`
to calculate it. The prompt builder already reads `snap.liquidity_score`. Can you
trace whether it's actually wired end-to-end before I ship this?

`schema.py`:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class PortfolioSnapshot:
    ticker: str
    price: float
    volume: int
    momentum_score: Optional[float] = None
    liquidity_score: Optional[float] = None
```

`snapshot_builder.py`:
```python
from schema import PortfolioSnapshot

def build_snapshot(ticker: str, price: float, volume: int) -> PortfolioSnapshot:
    return PortfolioSnapshot(ticker=ticker, price=price, volume=volume)
```

`enrich.py`:
```python
import dataclasses
from schema import PortfolioSnapshot

def attach_momentum(snap: PortfolioSnapshot, momentum: float) -> PortfolioSnapshot:
    return dataclasses.replace(snap, momentum_score=momentum)

def compute_liquidity_score(volume: int, avg_volume: float) -> float:
    return volume / avg_volume if avg_volume else 0.0
```

`prompt_builder.py`:
```python
def build_prompt(snap) -> str:
    return (
        f"Ticker {snap.ticker}: momentum={snap.momentum_score}, "
        f"liquidity={snap.liquidity_score}, price={snap.price}"
    )
```
