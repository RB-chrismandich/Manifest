---
max_turns: 20
timeout_seconds: 480
allowed_tools: [Skill, Read, Write, Edit, Grep, Glob, "Bash(mkdir:*)", "Bash(python3:*)", "Bash(pytest:*)"]
runs: 3
---
Save this as `pricing.py` and audit/fix it against the code constitution before we merge — that rate table looks like it shouldn't be sitting in the code.

```python
TAX_RATES = {
    "AL": 0.0400, "AK": 0.0000, "AZ": 0.0560, "AR": 0.0650, "CA": 0.0725,
    "CO": 0.0290, "CT": 0.0635, "DE": 0.0000, "FL": 0.0600, "GA": 0.0400,
    "HI": 0.0400, "ID": 0.0600, "IL": 0.0625, "IN": 0.0700, "IA": 0.0600,
    "KS": 0.0650, "KY": 0.0600, "LA": 0.0445, "ME": 0.0550, "MD": 0.0600,
}


def price_with_tax(amount, state):
    rate = TAX_RATES.get(state.upper(), 0.0)
    return round(amount * (1 + rate), 2)
```
