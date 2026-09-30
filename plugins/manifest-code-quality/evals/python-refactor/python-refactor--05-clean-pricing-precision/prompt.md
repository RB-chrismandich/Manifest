---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Here's our new pricing calculator. Anything to flag before I open the PR?

```python
# pricing/calculator.py
from decimal import Decimal
from typing import Final

TAX_RATE: Final[Decimal] = Decimal("0.08")


def calculate_total(subtotal: Decimal, discount_pct: Decimal = Decimal("0")) -> Decimal:
    """Return the subtotal after discount and tax, rounded to cents."""
    if discount_pct < 0 or discount_pct > 100:
        raise ValueError("discount_pct must be between 0 and 100")
    discounted = subtotal * (Decimal("1") - discount_pct / Decimal("100"))
    return (discounted * (Decimal("1") + TAX_RATE)).quantize(Decimal("0.01"))
```
