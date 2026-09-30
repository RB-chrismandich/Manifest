---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Write, Edit, Grep, Glob, "Bash(python3:*)", "Bash(pytest:*)"]
runs: 3
model: sonnet
---
Save this as `discount.py` and audit it against the code constitution — fix anything it flags.

```python
def apply_discount(price: float, percent: float) -> float:
    """Apply a percentage discount to a price.

    Raises ValueError if percent is outside [0, 100] or price is negative.
    """
    if not 0 <= percent <= 100:
        raise ValueError(f"percent must be between 0 and 100, got {percent}")
    if price < 0:
        raise ValueError(f"price must be non-negative, got {price}")
    return round(price * (1 - percent / 100), 2)
```
