---
max_turns: 10
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep, Bash]
runs: 3
---
Sandbox note: this sandbox forbids writing `.git/config` and blocks the macOS xcrun git shim, so the repo keeps its git metadata in `./r/gitmeta` instead of `.git`. Run every shell command from the directory you start in (don't `cd` elsewhere), and begin EVERY shell command — setup, git, and any smoke/test runner alike — with this prefix:

`G=/Library/Developer/CommandLineTools/usr/bin/git; if "$G" --version >/dev/null 2>&1; then mkdir -p "$PWD/.gitbin" && printf '#!/bin/sh\nexec "%s" "$@"\n' "$G" > "$PWD/.gitbin/git" && chmod +x "$PWD/.gitbin/git" && export PATH="$PWD/.gitbin:$PATH"; fi; export GIT_DIR="$PWD/r/gitmeta" GIT_WORK_TREE="$PWD/r";`

Right after `git init`, also run `mkdir -p r/gitmeta/info && echo gitmeta/ > r/gitmeta/info/exclude`.

Set up: create the directory `./r`, then run `git init -q --template= && git -c user.email=a@b -c user.name=t commit -q --allow-empty -m init` (with the prefix this initializes `./r`). Then, create an annotated git tag called `checkpoint-2026-09` on the current commit with message "pre-migration checkpoint", and show me it exists.
