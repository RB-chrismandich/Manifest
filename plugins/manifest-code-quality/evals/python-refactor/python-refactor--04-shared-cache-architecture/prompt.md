---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This module technically works but our team keeps stepping on each other's changes because every function reads and writes the same shared dict. Can you do a full audit -- architecture and anything else you spot?

```python
# orders/process.py
CACHE = {}

def process_order(order_id, user_input_notes, db_password="admin123"):
    CACHE[order_id] = {"notes": user_input_notes, "status": "pending"}
    conn_str = f"postgresql://admin:{db_password}@localhost/orders"
    if order_id in CACHE:
        CACHE[order_id]["status"] = "processing"
    return CACHE[order_id]
```
