---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We're hardening this service before a bigger customer signs on. Can you do a full refactor audit and give me a prioritized roadmap?

```go
// internal/db/query.go
package db

import (
	"database/sql"
	"fmt"
)

func GetUserByName(db *sql.DB, name string) (*sql.Rows, error) {
	query := fmt.Sprintf("SELECT id, email FROM users WHERE name = '%s'", name)
	return db.Query(query)
}
```

```go
// internal/auth/script.go
package auth

import "os/exec"

func RunUserScript(scriptName string) error {
	cmd := exec.Command("sh", "-c", "run-script "+scriptName)
	return cmd.Run()
}
```

```go
// internal/auth/session.go
package auth

import "fmt"

func generateSession(userID string) (string, error) {
	token, _ := createToken(userID)
	return token, nil
}

func createToken(userID string) (string, error) {
	if userID == "" {
		return "", fmt.Errorf("empty user id")
	}
	return "tok-" + userID, nil
}
```
