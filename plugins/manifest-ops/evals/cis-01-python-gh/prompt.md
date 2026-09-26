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

`tests/test_version.py`:
```
from ledger import __version__

def test_version():
    assert __version__ == "0.1.0"
```

Then set up CI/CD for this repo.
