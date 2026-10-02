---
type: llm
weight: 1
---
Score 1 only if the answer (a) identifies the SQL injection in `query = f"SELECT * FROM invoices WHERE customer_id = {customer_id}"` and proposes a Python-idiomatic parameterized-query fix (e.g. `cur.execute("SELECT * FROM invoices WHERE customer_id = ?", (customer_id,))`), and (b) does not frame the fix in Go-specific terms (e.g. does not talk about `fmt.Sprintf`, `database/sql`, or `go.mod`). Score 0 otherwise.
