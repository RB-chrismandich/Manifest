---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@github.com:acme/ledger.git`, and create these files exactly:

`pyproject.toml`:
```
[project]
name = "ledger"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`src/ledger/__init__.py`:
```
__version__ = "0.1.0"
```

`.github/workflows/ci.yml`:
```
# ORIGINAL-KEEP: hand-tuned by the platform team
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo tests
```

That scaffolding is the pre-existing state of the repo. Now, as a separate task: set up CI/CD for this repo.
