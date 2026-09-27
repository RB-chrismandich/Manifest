#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@github.com:acme/ledger.git
cat > 'pyproject.toml' <<'EOF_0'
[project]
name = "ledger"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF_0
mkdir -p 'src/ledger'
cat > 'src/ledger/__init__.py' <<'EOF_1'
__version__ = "0.1.0"
EOF_1
mkdir -p '.github/workflows'
cat > '.github/workflows/ci.yml' <<'EOF_2'
# ORIGINAL-KEEP: hand-tuned by the platform team
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo tests
EOF_2
