---
name: triage-bot-pr-flood
description: Use when several machine-generated PRs (Copilot/Jules/Palette/Bolt-style bots) are open and need dispositioning — duplicates, redundant no-ops, and repo-contradicting changes.
---
# Triage a Flood of Bot-Generated PRs

Automation bots produce duplicate and over-generalized PRs (e.g. four separate
PRs for the same one-line change). Disposition them by reading the *code*, not
the marketing-prose descriptions.

1. **Inventory** all open PRs with author, files, additions, CI state:
   `gh pr list --state open --json number,title,headRefName,author,additions,changedFiles`.
2. **Read the actual diff** for each (`gh pr diff <n>`). Bot PR bodies overstate;
   judge on the change itself.
3. **Detect exact duplicates by blob.** Two PRs touching the same file with the
   same resulting content are duplicates — compare the diff hunks/blob SHAs.
   Keep the better-titled one, **close the rest with a comment** naming the kept PR.
4. **Detect redundant no-ops.** If the change is already present in `main`
   (`grep` for the line), the PR is a no-op — close it, explaining it already shipped.
5. **Verify correctness of survivors** before merging: confirm refactors are
   behavior-preserving, and that UI/“cleanup” changes don't drop output the user
   needs (e.g. results printed *after* a cleared display are safe).
6. **Hold (do NOT merge) repo-contradicting changes.** Watch for a narrow change
   over-generalized into a blanket mandate that conflicts with the repo's real
   conventions (e.g. "deprecate all `.sh` for `.py`" or "prohibit `~` paths" in a
   repo that intentionally uses both). Post a review listing the specific
   blockers; let the bot revise.
7. **Re-check mergeability after each merge** (same-file PRs go `UNKNOWN` →
   re-poll until `CLEAN`), merge with the repo's convention (squash), delete branch.
8. **Flag the automation** if it's generating churn — recommend tightening dedup
   and feeding it the repo conventions up front.

## Sub-agent dispatch

When ≥3 machine-generated PRs are open, dispatch one sub-agent per PR (or batch) to disposition it, then consolidate; below that, triage inline. Pick the mechanism per the shared Sub-Agent Selection Rules (`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `parallel_agent.py` / inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.
