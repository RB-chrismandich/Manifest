---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@gitlab.com:acme/relay.git`, and create these files exactly:

`go.mod`:
```
module gitlab.com/acme/relay

go 1.22
```

`main.go`:
```
package main

import "fmt"

func main() { fmt.Println("relay") }
```

`main_test.go`:
```
package main

import "testing"

func TestNothing(t *testing.T) {}
```

Then set up CI/CD for this repo.
