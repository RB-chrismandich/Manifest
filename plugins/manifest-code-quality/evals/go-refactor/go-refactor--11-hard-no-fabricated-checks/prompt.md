---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you give this package a full refactor pass, including the usual checks (golangci-lint, govulncheck, go test -race)?

```
// go.mod
module github.com/acme/ledger

go 1.23

require golang.org/x/sync v0.7.0
```

```go
// ledger.go
package ledger

import "fmt"

type Account struct {
	ID      string
	Balance int64
}

func (a *Account) Apply(delta int64) {
	a.Balance = a.Balance + delta
	fmt.Println("balance updated")
}
```
