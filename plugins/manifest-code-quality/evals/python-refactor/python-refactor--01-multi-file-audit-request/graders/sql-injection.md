---
type: llm
weight: 1
---
Score 1 only if the answer flags `query = f"SELECT * FROM invoices WHERE customer_id = {customer_id}"` in `billing/queries.py` as a SQL injection vulnerability (customer_id is interpolated directly into the query string) and rates it Critical/High severity, AND proposes a parameterized query fix (e.g. `cur.execute("SELECT * FROM invoices WHERE customer_id = ?", (customer_id,))`). Score 0 otherwise.
