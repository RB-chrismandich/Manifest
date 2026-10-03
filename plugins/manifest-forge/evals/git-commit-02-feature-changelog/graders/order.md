---
type: llm
focus: last_message
weight: 1
---
Pass if the sequence syncs with the remote and runs pre-commit/tests BEFORE committing, then commits and pushes. Because the working tree is dirty (the --json feature is written but uncommitted), a bare `git pull --rebase` before committing fails with "cannot pull with rebase: You have unstaged changes" — the sync MUST preserve the work, i.e. commit first then `git pull --rebase`, or use `git stash`/`git pull --rebase --autostash` and restore afterwards.
