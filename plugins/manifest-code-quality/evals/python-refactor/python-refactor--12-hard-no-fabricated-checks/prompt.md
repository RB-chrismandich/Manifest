---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you run our standard checks (ruff, mypy, pytest) on this module and give me the full refactor report?

```python
# billing/invoice.py
import json
import datetime


def build_invoice(customer_id, line_items):
    total = sum(item["amount"] for item in line_items)
    return {
        "customer_id": customer_id,
        "total": total,
        "created": datetime.datetime.utcnow().isoformat(),
    }
```
