#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/app.git
mkdir -p .github/workflows
cat > .markdownlint.jsonc <<'EOF'
{ "default": true, "MD013": false, "MD033": false }
EOF
cat > .github/ml-strict.jsonc <<'EOF'
{ "default": true }
EOF
cat > .github/workflows/docs.yml <<'EOF'
name: docs
on: [pull_request]
jobs:
  markdownlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx markdownlint-cli2 --config .github/ml-strict.jsonc "**/*.md"
EOF
