---
name: pr-triage-bots
description: Triage a queue of machine-generated PRs (Jules, Palette, Bolt, Copilot) — detect byte-identical duplicates, close redundant no-ops, merge verified micro-opts, and hold PRs that contradict repo conventions.
---
# Triage Bot-Generated PRs

Use when several automated PRs are open (often targeting the same file/region) and each needs a disposition: merge,
close, or hold.
Bots over-produce: duplicate one-line changes across many PRs, overstate in marketing-prose bodies, and over-generalize
narrow changes into blanket policy. Judge the diff, not the title.

Bot identities live in `configs/claude/config/review_bots.yml`, not hardcoded
here: for each bot in the registry with `role: author` (currently `palette`,
`bolt`) or `role: reviewer` (`copilot`, `jules`, when it opens a sibling PR),
identify its PRs per the entry's `identified_by` field — `author_login` for
copilot/jules (real bot accounts), `title_prefix`/`branch_prefix` for
palette/bolt (Jules personas with no distinct GitHub identity — see the
registry's notes for the verification evidence). Read the registry rather
than re-deriving these facts; add a bot by editing the registry, not this
skill.

1. **Inventory and group by touched file/region.** `gh pr list --state open --json
   number,title,headRefName,author,additions,changedFiles`, then `gh pr diff <n>` for each.
2. **Detect exact duplicates by blob, not by eyeball.** Compare the changed-blob hash across PRs (`gh pr diff` / `git
   ls-tree`); byte-identical blobs (same SHA) mean keep one, close the rest as duplicates with a comment naming the kept
   PR. Keep the better-titled one.
3. **Detect redundant no-ops.** After merging one in a duplicate set — or before merging anything — re-grep `main` for
   the change (e.g. `transient=True` already on the target line); already-shipped PRs are no-ops — close them,
   explaining the change already landed.
4. **Verify each non-trivial diff is behavior-preserving before merging.** For refactors/opts (e.g. `Counter` rewrite,
   set-comprehension), read the surrounding code and confirm semantics are unchanged and final output still renders —
   e.g. UI/"cleanup" changes must not drop output the user needs (results printed *after* a cleared display are safe).
   Merge only when verified.
5. **Hold (do NOT merge) repo-contradicting changes.** Watch for over-generalized mandates (e.g. "deprecate all `.sh`
   for `.py`", "prohibit `~` in paths") that conflict with how the repo actually works. Post a review naming the
   specific blocking rules and what to change; let the bot revise.
6. **Re-check mergeability against updated main between merges.** Sequential merges to the same file invalidate prior
   mergeability (`mergeable` goes `UNKNOWN`); wait for recompute, re-poll until `CLEAN`, then merge in order with the
   repo's convention (squash), delete branch.
7. **Sync and run the full suite after the batch.** Confirm the sequential merges composed cleanly (compile + tests). If
   new failures appear, rule out environment causes (e.g. signing-agent down failing temp-repo commits) before blaming a
   merge.
8. **Flag the automation churn.** When a bot produced N PRs for one change, note it so the bot's dedup/conventions can
   be tightened upstream — and feed it the repo conventions up front.

## Sub-agent dispatch

When ≥3 bot PRs are open, dispatch one sub-agent per PR (or batch) to triage it, then consolidate
dispositions; below that, triage inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or
`manifest parallel-agent` / inline on other assistants. Dispatched sub-agents execute their task directly and
do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.

> Merged from the former bot-pr-triage and triage-bot-pr-flood skills (specs/480, 2026-07).
