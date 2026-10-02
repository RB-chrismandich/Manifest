#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@github.com:acme/app.git
mkdir -p '.github/workflows'
cat > '.github/workflows/ci.yml' <<'EOF_0'
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: make test
EOF_0
cat > 'Makefile' <<'EOF_1'
test:
	@echo test
EOF_1
