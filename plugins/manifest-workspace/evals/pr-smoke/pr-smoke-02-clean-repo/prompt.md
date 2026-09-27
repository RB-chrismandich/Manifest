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

`README.md`:
```markdown
# demo

Tiny demo repo.
```

`hello.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
printf 'hello %s\n' "${1:-world}"
```

Commit them (`git add -A && git -c user.email=a@b -c user.name=t commit -qm init`). Then run the full PR smoke gates and tell me whether this is safe to open a PR from.
