---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
New field `rsi` on `WatchlistEntry` — can you confirm it's wired end to end before
I close the ticket?

```python
from dataclasses import dataclass, replace
from typing import Optional

@dataclass(frozen=True)
class WatchlistEntry:
    ticker: str
    price: float
    rsi: Optional[float] = None

def build_entry(ticker: str, price: float, rsi_value: float) -> WatchlistEntry:
    entry = WatchlistEntry(ticker=ticker, price=price)
    entry = replace(entry, rsi=rsi_value)
    return entry

def run(tickers: list[str]) -> list[WatchlistEntry]:
    out = []
    for t in tickers:
        price = fetch_price(t)
        rsi_value = compute_rsi(t)
        out.append(build_entry(t, price, rsi_value))
    return out

def render(entry: WatchlistEntry) -> str:
    return f"{entry.ticker}: RSI={entry.rsi}"
```
