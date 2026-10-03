---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Heads up: this repo has both a `go.mod` and a `package.json` (the JSON file is only config for our commitlint pre-commit hook, there's no real JS logic in here) — here's the actual code to refactor, `orders/handler.go`:

```go
type Order struct {
	ID    string
	Total float64
}

func GetOrder(db *sql.DB, orderID string) (*Order, error) {
	q := "SELECT id, total FROM orders WHERE id = " + orderID
	row := db.QueryRow(q)

	var o Order
	err := row.Scan(&o.ID, &o.Total)
	if err != nil {
		log.Println(err)
	}
	return &o, nil
}
```
