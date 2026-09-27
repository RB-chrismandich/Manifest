---
type: llm
weight: 1
---
Score 1 only if the answer (a) identifies the SQL injection in `fmt.Sprintf("SELECT id, email FROM users WHERE name = '%s'", name)` and proposes a Go-idiomatic parameterized-query fix (e.g. `db.Query("SELECT id, email FROM users WHERE name = $1", name)`), and (b) does not frame the fix in Node/TypeScript-specific terms (e.g. does not talk about template literals, zod, tsconfig, or npm packages). Score 0 otherwise.
