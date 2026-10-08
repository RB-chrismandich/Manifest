#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/app.git
mkdir -p .github/workflows
cat > .github/workflows/checks.yml <<'EOF'
name: checks
on: [pull_request]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Verify generated files are up to date
        run: |
          make generate
          git diff --exit-code
      - name: Unit tests
        run: go test ./...
EOF
cat > Makefile <<'EOF'
generate:
	go generate ./...
EOF
