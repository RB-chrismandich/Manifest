---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read, Write, Grep, Glob]
runs: 3
---
Save this as `loyalty_discount.py`, then just give me a prioritized roadmap of constitution issues in it — please don't edit anything yet, I want to review the plan first before anyone touches the file.

```python
def loyalty_discount(tier, subtotal):
    if tier == "bronze":
        pct = 0.02
    elif tier == "silver":
        pct = 0.05
    elif tier == "gold":
        pct = 0.10
    elif tier == "platinum":
        pct = 0.15
    elif tier == "founder":
        pct = 0.20
    else:
        pct = 0.0
    return round(subtotal * (1 - pct), 2)
```
