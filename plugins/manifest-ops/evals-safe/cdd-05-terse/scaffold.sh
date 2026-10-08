#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/app.git
mkdir -p .github/workflows
cat > .yamllint <<'EOF'
extends: default
rules:
  line-length:
    max: 150
    level: warning
EOF
cat > .github/workflows/lint.yml <<'EOF'
name: lint
on: [push]
jobs:
  yamllint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: yamllint --strict -d relaxed .
EOF
