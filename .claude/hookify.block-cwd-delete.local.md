---
name: block-cwd-delete
enabled: true
event: bash
action: block
conditions:
  - field: command
    operator: regex_match
    pattern: (git\s+(-C\s+\S+\s+)?worktree\s+remove|rm\s+-\S*[rR]\S*\s+\S*worktrees?/)
  - field: command
    operator: not_contains
    pattern: cwd-verified
---

🛑 **Worktree/directory removal blocked — verify it is not this session's cwd first**

Deleting the directory the session is running in breaks EVERY subsequent
process spawn (hooks, Bash tool) with a misleading
`posix_spawn '/bin/sh' ENOENT` error — posix_spawn reports ENOENT for a
missing child working directory, and Node attributes it to the binary
(incident: 2026-07-03, rename-skillz worktree).

Before re-running:

1. Check `pwd -P` — the removal target must NOT be the session cwd or an
   ancestor of it. Remember the shell may have `cd`'d; check the session's
   original start directory too.
2. If the target IS the session cwd: use the ExitWorktree tool first (for
   harness worktrees), or leave cleanup to after the session ends.
3. If verified safe, re-run the same command with the marker appended:
   `<command>  # cwd-verified`
