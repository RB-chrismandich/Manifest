---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Builds a branch from origin/main containing only c0ffee1 and c0ffee2 (cherry-pick or rebase --onto).
2. Updates the MR safely: force-push with `--force-with-lease` to feat/export, OR push a new branch and open a new MR targeting main while closing !31.
3. Speaks in GitLab terms (MR / target branch / glab or web UI) and does not rely on gh commands.
