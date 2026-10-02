---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Sandbox note: this sandbox forbids writing `.git/config` and blocks the macOS xcrun git shim, so the repo keeps its git metadata in `./repo/gitmeta` instead of `.git`. Run every shell command from the directory you start in (don't `cd` elsewhere), and begin EVERY shell command — setup, git, and any smoke/test runner alike — with this prefix:

`G=/Library/Developer/CommandLineTools/usr/bin/git; if "$G" --version >/dev/null 2>&1; then mkdir -p "$PWD/.gitbin" && printf '#!/bin/sh\nexec "%s" "$@"\n' "$G" > "$PWD/.gitbin/git" && chmod +x "$PWD/.gitbin/git" && export PATH="$PWD/.gitbin:$PATH"; fi; export GIT_DIR="$PWD/repo/gitmeta" GIT_WORK_TREE="$PWD/repo";`

Right after `git init`, also run `mkdir -p repo/gitmeta/info && echo gitmeta/ > repo/gitmeta/info/exclude`.

Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). Set up the scenario first: create the directory `./repo` and run `git init -q --template=` (with the prefix this initializes `./repo`), create `./repo/app.py` containing `print("v1")`, and commit it (`git -c user.email=a@b -c user.name=t commit -qam init` after `git add -A`); then change `./repo/app.py` to `print("v2")` and create an untracked `./repo/notes.txt` — leave both uncommitted.

Step 1: write a session checkpoint for goal "ship the v2 banner" (no live operations; tests not run yet).
Step 2: then simulate time passing — in ./repo, commit the app.py change (`git add -A && git -c user.email=a@b -c user.name=t commit -qm v2`).
Step 3: now act as the fresh session resuming from that checkpoint. Should it trust the checkpoint as-is? Tell me what changed.
