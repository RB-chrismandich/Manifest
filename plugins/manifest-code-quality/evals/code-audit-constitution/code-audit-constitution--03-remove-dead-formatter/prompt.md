---
max_turns: 20
timeout_seconds: 480
allowed_tools: [Skill, Read, Write, Edit, Grep, Glob, "Bash(mkdir:*)", "Bash(python3:*)", "Bash(pytest:*)"]
runs: 3
model: sonnet
---
Reviewing this before merge — run a constitution audit on `pricing/format.py` and clean up anything it flags. We migrated everything to the v2 formatter a while back, and this is the only other file in the module that touches either function.

Save both files as shown:

```python
# pricing/format.py
def format_price_v1(amount):
    return "$%.2f" % amount


def format_price_v2(amount, currency="USD"):
    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{amount:.2f}"
```

```python
# pricing/invoice.py
from pricing.format import format_price_v2


def render_line(item_name, amount, currency="USD"):
    return f"{item_name}: {format_price_v2(amount, currency)}"
```
