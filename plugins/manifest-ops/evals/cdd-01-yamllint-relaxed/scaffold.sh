#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@github.com:acme/app.git
cat > '.yamllint' <<'EOF_0'
extends: default
rules:
  line-length:
    max: 150
    level: warning
EOF_0
mkdir -p '.github/workflows'
cat > '.github/workflows/lint.yml' <<'EOF_1'
name: lint
on: [push, pull_request]
jobs:
  yamllint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: yamllint
        run: yamllint --strict -d relaxed .
EOF_1
