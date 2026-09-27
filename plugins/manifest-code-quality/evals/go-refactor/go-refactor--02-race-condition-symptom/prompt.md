---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
`go test -race` flagged something in our metrics package under load, and separately I noticed this admin token sitting in the code -- can you do a full pass on these two files, not just the race, and prioritize what needs fixing?

```go
// internal/metrics/counter.go
package metrics

import "fmt"

const adminToken = "sk-admin-9f8e7d6c5b4a"

var requestCount int

func IncrementAndLog() {
	requestCount++
	if requestCount%100 == 0 {
		go func() {
			fmt.Println("count", requestCount, "token", adminToken)
		}()
	}
}
```

```go
// internal/metrics/limiter.go
package metrics

type RateLimiter struct {
	Max int
}

func (r *RateLimiter) Allow(current int) bool {
	return current < r.Max
}
```
