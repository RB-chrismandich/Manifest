---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our spec-consistency check flagged `momentum_score` as a coverage gap: it's
referenced in the alert-prompt spec but `plan.md` never lists a task to populate
it. Here's the current schema, builder, and prompt code — is this a real gap, and
if so where does the fix actually need to go?

`schema.py`:
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AlertContext:
    ticker: str
    price: float
    momentum_score: float | None = None
    volatility_flag: bool | None = None
```

`builder.py`:
```python
import dataclasses
from schema import AlertContext

def compute_volatility_flag(price: float) -> bool:
    return price < 1.0

def compute_momentum_score(ticker: str) -> float:
    # real calculation against price history, omitted for brevity
    ...

def build_alert_context(ticker: str, price: float) -> AlertContext:
    ctx = AlertContext(ticker=ticker, price=price)
    ctx = dataclasses.replace(ctx, volatility_flag=compute_volatility_flag(price))
    return ctx
```

`prompt.py`:
```python
def build_alert_prompt(ctx) -> str:
    return f"{ctx.ticker}: momentum={ctx.momentum_score}, volatile={ctx.volatility_flag}"
```
