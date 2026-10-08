#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/app.git
mkdir -p .github/workflows
cat > .github/workflows/ci.yml <<'EOF'
name: ci
on: [pull_request]
jobs:
  lint-and-generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint
        run: make lint
      - name: Verify generated files
        run: make generate && git diff --exit-code
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make e2e
EOF
cat > Makefile <<'EOF'
lint:
	@echo lint
generate:
	@echo generate
e2e:
	@echo e2e
EOF
