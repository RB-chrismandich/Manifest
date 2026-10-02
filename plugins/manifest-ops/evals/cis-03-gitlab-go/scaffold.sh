#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@gitlab.com:acme/relay.git
cat > 'go.mod' <<'EOF_0'
module gitlab.com/acme/relay

go 1.22
EOF_0
cat > 'main.go' <<'EOF_1'
package main

import "fmt"

func main() { fmt.Println("relay") }
EOF_1
cat > 'main_test.go' <<'EOF_2'
package main

import "testing"

func TestNothing(t *testing.T) {}
EOF_2
