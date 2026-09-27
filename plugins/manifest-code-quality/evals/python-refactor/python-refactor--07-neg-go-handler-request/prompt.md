---
max_turns: 10
timeout_seconds: 240
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you refactor this Go handler for security issues before we ship it?

```go
package handlers

import (
	"database/sql"
	"fmt"
	"net/http"
)

func SearchUsers(db *sql.DB, w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("name")
	query := fmt.Sprintf("SELECT id, email FROM users WHERE name = '%s'", name)
	rows, err := db.Query(query)
	if err != nil {
		http.Error(w, "query failed", http.StatusInternalServerError)
		return
	}
	defer rows.Close()
}
```
