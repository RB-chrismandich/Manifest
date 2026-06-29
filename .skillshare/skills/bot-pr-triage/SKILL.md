---
name: bot-pr-triage
description: Triage a queue of bot-generated PRs (Jules, Palette, Bolt, Copilot) — detect byte-identical duplicates, merge sound micro-opts, close redundant ones, and hold PRs that contradict repo conventions
---
# Bot-Generated PR Triage

Use when several automated PRs target the same file/region and you must decide merge/close/hold per PR. Bots over-produce: duplicate one-line changes across many PRs and over-generalize narrow changes into blanket policy.

1. **List and group by touched file/region.** `gh pr list` then `gh pr diff <n>` for each. Bot descriptions are marketing — judge the diff, not the title.
2. **Detect exact duplicates by blob, not by eyeball.** Compare the changed-blob hash across PRs (`gh pr diff` / `git ls-tree`); byte-identical blobs (same SHA) mean keep one, close the rest as duplicates. Keep the better-titled one.
3. **Check for already-merged redundancy.** After merging one in a duplicate set, re-grep `main` for the change (e.g. `transient=True` already on the target line) — remaining PRs become no-ops; close them with an explanatory comment.
4. **Verify each non-trivial diff is behavior-preserving before merging.** For refactors/opts (e.g. `Counter` rewrite, set-comprehension), read the surrounding code and confirm semantics are unchanged and final output still renders. Merge only when verified.
5. **Hold PRs that contradict repo conventions.** Watch for over-generalized mandates (e.g. "deprecate all `.sh` for `.py`", "prohibit `~` in paths") that conflict with how the repo actually works. Post a review naming the specific blocking rules and what to change — do not merge.
6. **Re-check mergeability against updated main between merges.** Sequential merges to the same file invalidate prior mergeability; `sleep` for recompute, re-query `mergeable`, then merge in order.
7. **Sync and run the full suite after the batch.** Confirm the sequential merges composed cleanly (compile + tests). If new failures appear, rule out environment causes (e.g. signing-agent down failing temp-repo commits) before blaming a merge.
8. **Flag the automation churn.** When a bot produced N PRs for one change, note it so the bot's dedup/conventions can be tightened upstream.

## Sub-agent dispatch

When ≥3 bot PRs are open, dispatch one sub-agent per PR (or batch) to triage it, then consolidate dispositions; below that, triage inline. Pick the mechanism per the shared Sub-Agent Selection Rules (`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `parallel_agent.py` / inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.
