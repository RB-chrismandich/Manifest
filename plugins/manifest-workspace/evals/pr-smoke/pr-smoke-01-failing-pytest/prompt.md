---
max_turns: 35
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Sandbox note: this sandbox forbids writing `.git/config` and blocks the macOS xcrun git shim, so the repo keeps its git metadata in `./gitmeta` instead of `.git`. Run every shell command from the directory you start in (don't `cd` elsewhere), and begin EVERY shell command — setup, git, and any smoke/test runner alike — with this prefix:

`G=/Library/Developer/CommandLineTools/usr/bin/git; if "$G" --version >/dev/null 2>&1; then mkdir -p "$PWD/.gitbin" && printf '#!/bin/sh\nexec "%s" "$@"\n' "$G" > "$PWD/.gitbin/git" && chmod +x "$PWD/.gitbin/git" && export PATH="$PWD/.gitbin:$PATH"; fi; export GIT_DIR="$PWD/gitmeta" GIT_WORK_TREE="$PWD";`

Right after `git init`, also run `mkdir -p gitmeta/info && printf 'gitmeta/\n.gitbin/\n' > gitmeta/info/exclude`.

First set up the repo in the current directory: run `git init -q --template=`, then create these files exactly:

`src/calc.py`:
```python
def add(a, b):
    return a - b
```

`tests/test_calc.py`:
```python
from src.calc import add

def test_add():
    assert add(2, 3) == 5
```

and an empty `src/__init__.py`. Then run the PR smoke regression gates on this repo (full run, not quick) and tell me the verdict and the first failing gate.
