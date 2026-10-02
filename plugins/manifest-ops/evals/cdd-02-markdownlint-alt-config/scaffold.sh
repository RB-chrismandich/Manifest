#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@github.com:acme/app.git
cat > '.markdownlint.jsonc' <<'EOF_0'
{ "default": true, "MD013": false, "MD033": false }
EOF_0
mkdir -p '.github'
cat > '.github/ml-strict.jsonc' <<'EOF_1'
{ "default": true }
EOF_1
mkdir -p '.github/workflows'
cat > '.github/workflows/docs.yml' <<'EOF_2'
name: docs
on: [pull_request]
jobs:
  markdownlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx markdownlint-cli2 --config .github/ml-strict.jsonc "**/*.md"
EOF_2
