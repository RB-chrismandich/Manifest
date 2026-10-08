#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/ledger.git
mkdir -p src/ledger .github/workflows
cat > pyproject.toml <<'EOF'
[project]
name = "ledger"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
cat > src/ledger/__init__.py <<'EOF'
__version__ = "0.1.0"
EOF
cat > .github/workflows/ci.yml <<'EOF'
# ORIGINAL-KEEP: hand-tuned by the platform team
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo tests
EOF
