---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
We're about to onboard a bigger customer onto this billing service. Can you do a full refactor audit and give me a prioritized roadmap of what to fix before then?

```python
# billing/queries.py
import sqlite3

def get_invoices_for_customer(customer_id):
    conn = sqlite3.connect("billing.db")
    cur = conn.cursor()
    query = f"SELECT * FROM invoices WHERE customer_id = {customer_id}"
    cur.execute(query)
    return cur.fetchall()
```

```python
# billing/config.py
STRIPE_API_KEY = "hardcoded-example-token"  # gitleaks:allow

def get_client():
    import stripe
    stripe.api_key = STRIPE_API_KEY
    return stripe
```

```python
# billing/report.py
def generate_report(invoices, customer_name, discount_pct, tax_pct, currency, include_tax, include_discount, notes):
    total = 0
    try:
        for inv in invoices:
            amt = inv["amount"]
            if include_discount:
                amt = amt - (amt * discount_pct / 100)
            if include_tax:
                amt = amt + (amt * tax_pct / 100)
            total += amt
        print(f"Report for {customer_name}: {total} {currency}")
        return total
    except:
        pass
```
