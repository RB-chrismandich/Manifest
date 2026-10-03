---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Tells the user to abort the in-progress rebase (`git rebase --abort`).
2. Moves ONLY f00d001 and f00d002 onto origin/main — via cherry-pick onto a fresh branch or `git rebase --onto origin/main ab12cd3` — leaving the auth commits behind.
3. Does not try to resolve the auth conflicts in session.ts.
4. Updates the PR safely: either force-push with `--force-with-lease`, or push a new branch and supersede #214.
