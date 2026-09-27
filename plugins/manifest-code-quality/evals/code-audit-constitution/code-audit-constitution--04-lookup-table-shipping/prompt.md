---
max_turns: 20
timeout_seconds: 480
allowed_tools: [Skill, Read, Write, Edit, Grep, Glob, "Bash(python3:*)", "Bash(pytest:*)"]
runs: 3
---
Can you save this as `shipping.py` and audit it against our code constitution? Every time we add a region we just bolt on another elif — feels like it's due for a cleanup.

```python
def shipping_cost(region, weight_kg):
    if region == "US":
        base = 5.00
    elif region == "CA":
        base = 7.50
    elif region == "MX":
        base = 9.00
    elif region == "EU":
        base = 12.00
    elif region == "UK":
        base = 11.00
    elif region == "AU":
        base = 15.00
    else:
        base = 20.00
    return round(base + weight_kg * 0.5, 2)
```
