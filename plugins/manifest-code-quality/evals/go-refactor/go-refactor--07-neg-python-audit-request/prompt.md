---
max_turns: 10
timeout_seconds: 240
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you audit this Python billing helper for issues before we merge it?

```python
def get_invoice(customer_id):
    conn = sqlite3.connect("billing.db")
    cur = conn.cursor()
    query = f"SELECT * FROM invoices WHERE customer_id = {customer_id}"
    cur.execute(query)
    return cur.fetchone()
```
