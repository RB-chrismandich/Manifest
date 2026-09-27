---
type: llm
weight: 1
---
Score 1 only if the answer flags `fmt.Sprintf("SELECT id, email FROM users WHERE name = '%s'", name)` in `internal/db/query.go` as a SQL injection vulnerability, rates it Critical, AND proposes a parameterized-query fix (e.g. `db.Query("SELECT id, email FROM users WHERE name = $1", name)` or `?` placeholder). Score 0 otherwise.
