#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@gitlab.com:acme/relay.git
cat > go.mod <<'EOF'
module gitlab.com/acme/relay

go 1.22
EOF
cat > main.go <<'EOF'
package main

import "fmt"

func main() { fmt.Println("relay") }
EOF
cat > main_test.go <<'EOF'
package main

import "testing"

func TestNothing(t *testing.T) {}
EOF
