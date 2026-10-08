#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/app.git
mkdir -p .github/workflows
cat > .github/workflows/ci.yml <<'EOF'
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: make test
EOF
cat > Makefile <<'EOF'
test:
	@echo test
EOF
