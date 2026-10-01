---
type: llm
weight: 1
---
Score 1 only if the answer gives Go-specific findings: it identifies BOTH (1) `fmt.Sprintf` interpolating `username` directly into the SQL query string as a SQL-injection vulnerability, recommending a parameterized query (e.g. `db.QueryRow("SELECT id, email FROM users WHERE username = ?", username)`) instead of string formatting, AND (2) `_ = row.Scan(&u.ID, &u.Email)` as discarding the error returned by `Scan` (with the function unconditionally returning a `nil` error), recommending checking and returning/wrapping that error instead of discarding it. Score 0 if either finding is missing, or if the answer gives generic/IaC/shell/Python advice instead of Go-specific fixes.
