---
type: llm
weight: 1
---
Score 1 only if the answer (a) identifies the SQL injection in `fmt.Sprintf("SELECT id, email FROM users WHERE name = '%s'", name)` and proposes a Go-idiomatic parameterized-query fix (e.g. `db.Query("SELECT id, email FROM users WHERE name = $1", name)` or using `?` placeholders), and (b) does not frame the fix or discussion in Python-specific terms (e.g. does not talk about f-strings, `cur.execute`, pyproject.toml, or Python type hints). Score 0 otherwise.
