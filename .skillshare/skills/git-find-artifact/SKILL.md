---
name: git-find-artifact
description: Use when a referenced file (spec, plan, doc, config) does not exist at the given path on the current branch — search worktrees, all branches, and git history before assuming it is missing or asking the user.
---
# Locate a Missing Artifact Across Git

When a task references a file by path and it is not present in the working tree, do NOT conclude it is missing (or block on the user) until you have searched the rest of the repository's git surface. Files frequently live on a sibling branch, an untracked worktree, or a past commit.

Run these steps in order and stop as soon as the artifact is found.

1. **Confirm the literal path is absent and scan obvious siblings.** List the parent directory and `find` for the basename (and close variants) under the repo root:
   `find <repo> -name '*<distinctive-stem>*' 2>/dev/null` and `ls -la <expected-parent-dir>`.

2. **Enumerate worktrees and branches.** A spec is often committed on the design/feature branch, not the one you are on:
   `git worktree list` and `git branch -a`. Grep the branch list for keywords from the filename (e.g. `git branch -a | grep -i 'audit\|promote'`).

3. **Search git history across ALL refs for the filename.** This finds it even on remote-only or stale branches:
   `git log --all --oneline -- '*<distinctive-stem>*'`. Note the branch/SHA from the result.

4. **List the file's exact path on the branch where it lives** (the path may differ from the one you were given):
   `git ls-tree -r --name-only <branch> | grep -i '<stem>'`.

5. **Read the artifact directly from that ref without switching branches:**
   `git show <branch>:<path/to/file>`. Use this content to proceed.

6. **Decide placement before editing.** If work must happen against this artifact, either `git switch <branch>` (untracked files carry over), or `git checkout <branch> -- <path>` to pull just the file onto your current branch. Prefer doing the work on the branch where the spec already lives, and say so explicitly.

7. **Only after all of the above come up empty**, report it as genuinely absent — name where you looked (worktrees, all branches, full history) so the user knows the search was exhaustive, then ask how to proceed.
