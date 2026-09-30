---
max_turns: 30
timeout_seconds: 900
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(go:*)", "Bash(command:*)"]
runs: 3
model: sonnet
---
Our CI has been red on this branch for the last two runs and I can't tell why. Here's the Go package — save these three files in the current directory exactly as given, then check it and tell me what's broken before I push again.

`go.mod`:
```
module tinycalc

go 1.21
```

`main.go`:
```go
package tinycalc

func Add(a, b int) int {
	return a + b
}

func Multiply(a, b int) int {
	return a * b
}
```

`main_test.go`:
```go
package tinycalc

import "testing"

func TestAdd(t *testing.T) {
	if Add(2, 3) != 6 {
		t.Errorf("Add(2, 3) = %d, want 6", Add(2, 3))
	}
}

func TestMultiply(t *testing.T) {
	if Multiply(3, 4) != 12 {
		t.Errorf("Multiply(3, 4) = %d, want 12", Multiply(3, 4))
	}
}
```
