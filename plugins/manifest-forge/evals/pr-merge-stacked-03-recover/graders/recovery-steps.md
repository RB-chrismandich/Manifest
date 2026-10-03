---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Restores the deleted base branch (feat-parser) on the remote, pointing at a real commit (e.g. its old head SHA).
2. Reopens #88 after the branch exists again (e.g. `gh pr reopen 88`).
3. Retargets #88 to main.
4. Notes that #88 still carries #87's unmerged commits and removes them (e.g. `git rebase --onto origin/main
   <feat-parser-sha> <88-branch>` + `git push --force-with-lease`) unless the user wants them shipped.
5. Deletes the temporary restored branch only after the retarget.
Fail if it tells the user they must open a brand-new PR as the only option.
