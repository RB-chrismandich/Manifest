---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Every report row shows "sector PE=None" even though I added the `sector_pe_ratio`
field months ago. Here's the whole pipeline — what's missing?

```python
class TradeContext:
    def __init__(self, ticker, price, volume, sector_pe_ratio=None):
        self.ticker = ticker
        self.price = price
        self.volume = volume
        self.sector_pe_ratio = sector_pe_ratio

def build_context(ticker, price, volume) -> TradeContext:
    return TradeContext(ticker=ticker, price=price, volume=volume)

def render_report(ctx: TradeContext) -> str:
    return f"{ctx.ticker}: price={ctx.price}, sector PE={ctx.sector_pe_ratio}"
```
