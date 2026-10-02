---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Please refactor this Go handler for security and correctness.

```go
func GetUser(db *sql.DB, username string) (*User, error) {
	query := fmt.Sprintf("SELECT id, email FROM users WHERE username = '%s'", username)
	row := db.QueryRow(query)

	var u User
	_ = row.Scan(&u.ID, &u.Email)
	return &u, nil
}
```
