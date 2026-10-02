---
max_turns: 35
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Sandbox note: the macOS xcrun git shim fails in this sandbox, so begin EVERY shell command you run (including the test runner) with `G=/Library/Developer/CommandLineTools/usr/bin/git; if "$G" --version >/dev/null 2>&1; then mkdir -p "$PWD/.gitbin" && printf '#!/bin/sh\nexec "%s" "$@"\n' "$G" > "$PWD/.gitbin/git" && chmod +x "$PWD/.gitbin/git" && export PATH="$PWD/.gitbin:$PATH"; fi;` (a no-op where that path doesn't exist).

Create `test_author.py` in the current directory with exactly:

```python
import subprocess

def git_author():
    return subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()

def test_author_is_set():
    assert git_author().endswith("@example.com")
```

This passes on my laptop but fails in CI. Why, and fix the test so it's reliable everywhere. Run it to show it passes (with pytest, or convert it to stdlib `unittest` if pytest isn't usable here).
