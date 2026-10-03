---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our release tooling shells out to a small Go token generator — can you refactor both pieces before we wire this into CI?

`run-release.sh`:

```bash
#!/usr/bin/env bash
set -eo pipefail

CONFIG_PATH="$1"
source "$CONFIG_PATH"

./bin/token-gen --service "$SERVICE_NAME" > /tmp/token
```

`token-gen/main.go`:

```go
package main

import (
	"fmt"
	"math/rand"
	"time"
)

func generateToken() string {
	rand.Seed(time.Now().UnixNano())
	return fmt.Sprintf("%x", rand.Int63())
}

func main() {
	fmt.Println(generateToken())
}
```
