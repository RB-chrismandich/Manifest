---
name: repo-clean
description: "PR/MR + branch cleanup sweep: review every open PR and stale/merged/gone branch, then after you confirm close the dead PRs and prune branches (GitHub/GitLab/local). For any \"tidy up my repo\" ask spanning both; pick over pr-review or branch-clean."
---

# Repository Hygiene Sweep

Give the user a single, organized picture of everything outstanding — every open
PR/MR and every prunable branch — with a concrete next step for each, then act
on the stale items once they confirm.

This skill is an **orchestrator**. It does not reimplement PR or branch logic;
it composes two existing, hardened skills:

- `pr-review` → `~/.claude/scripts/pr_review.sh` (platform detection, CI rollup,
  mergeability, per-PR disposition). Analysis-only.
- `branch-clean` → `~/.claude/scripts/branch_clean.sh` (merged / `[gone]` /
  stale grouping, protected-glob and current-branch guards). Dry-run by default.

Reusing them means this skill inherits their safety rails and stays correct when
they improve — don't duplicate their internals here.

## When to use

- The user wants an overview of the PR queue *and* a cleanup pass in one go.
- "Review my open PRs and close the stale ones."
- "Clean up old branches locally and on GitHub/GitLab."
- Periodic repo tidy-up after a batch of merges.

## Operating principle: report first, act on confirmation

The default flow is **gather → report → confirm → act**. Nothing is closed or
deleted until the user has seen the candidates and said go (or passed `--apply`).
This mirrors the repo convention that destructive, outward-facing actions are
reversible-friendly and explicitly authorized. Closing a PR and deleting a
branch are hard to take back, so the friction is deliberate.

## Workflow

### 1. Gather (read-only)

Run three read-only sources and capture their output. None mutates anything.

```bash
# (a) Per-PR disposition: mergeability, checks, staleness, superseded
~/.claude/scripts/pr_review.sh --json            # add --stale-days N to tune

# (b) Conservative branch candidates (merged-by-fast-forward / [gone] / stale-by-date)
~/.claude/scripts/branch_clean.sh                # dry-run; add --stale-days N

# (c) Squash-merge-aware enrichment the other two can't provide:
#     open-PR diff sizes (empty-PR detection) + branch<->PR-state correlation
python3 "<this-skill-dir>/scripts/hygiene_gather.py"   # --platform / --stale-days N / --protect glob
```

**Why (c) is not optional.** Two real gaps make the first two sources lie on a
normal repo:

- `pr_review.sh` has no changes-count, and a zero-diff PR produces no checks, so
  its disposition defaults to `merge`. An **empty no-op PR therefore looks
  mergeable.** `hygiene_gather.py` reports `empty_prs` (PRs with 0 changed
  files) — treat any of those as **closeable**, overriding the `merge`
  disposition.
- `branch_clean.sh` finds merged branches via `git branch --merged`, which only
  sees fast-forward ancestry. On a **squash-merge repo the merged branch's tip
  is never an ancestor of the default branch**, so it reports almost nothing and
  the real clutter (often dozens of branches) stays hidden. `hygiene_gather.py`
  correlates each local/remote branch to its PR/MR merge-state and classifies it
  (see step 2), which is what surfaces the actual cleanup.

Use a consistent staleness window across all three (default to the repo's
configured value; if the user names a number, pass the same `--stale-days N` to
each). Detect the platform with `~/.claude/scripts/git_platform.sh` if you need
to name it (github / gitlab / git).

Handle the distinct failure modes: an **empty queue / no candidates** is a clean
result; an **unauthenticated or missing CLI** is *not* — `hygiene_gather.py`
reports those in its `errors` array. Surface them as "couldn't look", never as
"all clean", because a silent auth failure would otherwise read as a tidy repo.
GitLab note: `hygiene_gather.py` correlates MR state but cannot size MRs for
empty-detection (glab's list has no changes count) — it flags this, and you can
spot-check a suspected no-op with `glab mr diff <iid>`.

### 2. Report — break everything into sections

Synthesize both outputs into one report. The grouping and the per-item next step
are the value the user is asking for, so do this thoughtfully rather than dumping
raw script output. Use this structure:

```markdown
# Repo Hygiene — <repo> (<platform>)
_<date> · stale threshold: <N>d_

## Open PRs/MRs (<total>)

### ✅ Ready to merge (<n>)
- **#<num>** <title> — `<branch>` · checks ✓ · <age>
  → Next: merge — `~/.claude/scripts/git_ops.sh pr-merge <num>`

### 🔧 Needs work (<n>)
- **#<num>** <title> — <conflict / failing checks / draft-with-activity>
  → Next: <rebase | fix CI | finish draft>

### 🗑️ Stale / closeable (<n>)
- **#<num>** <title> — <reason: EMPTY no-op (0 files / +0/-0) | branch already merged | superseded by #X | >Nd no activity>
  → Next: close

### 🟢 Keep (<n>)
- **#<num>** <title> — <active draft / pending checks / ongoing>

## Branches

Classified by PR/MR merge-state (from `hygiene_gather.py`), not just ancestry —
so squash-merged branches show up as safe. Split into **safe** (auto-deletable on
confirm) vs **confirm-individually** (may hold unmerged work).

### ✅ Safe to delete (<n>)  — local
- `<branch>` — merged via #<num> (squash) | merged (fast-forward) | `[gone]` (remote deleted)

### ⚠️ Confirm individually (<n>)
- `<branch>` — closed-unmerged (PR #<num> closed without merging) | no PR + stale >Nd
  → may contain real work; never auto-delete — confirm each.

### 🌐 Remote (origin) (<n>)
- safe: `<branch>` (merged via #<num>) · confirm: `<branch>` (closed-unmerged / no-PR)
  → remote deletion is opt-in (`--include-remote` / explicit request) even when safe.

### 🟢 Keep
- local with an open PR or recent unmerged work; remote backing an open PR.

### 🔒 Protected / current — never deleted: <list>

## Recommended actions
1. **Close stale PRs:** #<a>, #<b>
2. **Prune branches:** `<x>`, `<y>` (local; add remote on request)
3. **Merge when ready:** #<c>

_Reply **apply** to close the stale PRs and prune the stale branches, or tell me
which specific items to act on._
```

Keep rationales to one line each — the user is scanning. If a section is empty,
keep its heading with `(0)` so the report reads as complete coverage, not a
silent omission.

### 3. Act — only after confirmation

When the user confirms (or invoked with `--apply` / "apply"), act on exactly the
items you put in the **Stale / closeable** and **Safe to delete** lists — never
on `keep`, `needs-work`, or `confirm-individually` items without a separate OK.

**Close stale PRs** (including the empty no-ops) via `git_ops.sh pr-close`
(routes to `gh pr close` / `glab mr close`). Leave a short comment so the
trail explains *why*:

```bash
~/.claude/scripts/git_ops.sh pr-close <num> --comment "Closing as stale: <reason>. Reopen if still needed."
```

**Delete branches**, by class. The split matters because force-delete is only
safe when something else proves the work is preserved:

```bash
# merged-ff + [gone]: hand to branch_clean.sh — its guarded -d path is enough
~/.claude/scripts/branch_clean.sh --apply              # local, prompts (--yes to skip)

# merged-pr (squash-merged): branch_clean refuses these (-d sees them as unmerged),
# but the merged PR proves the work landed, so -D is safe HERE and only here.
git branch -D <branch>                                 # only for verified merged-pr branches

# remote, opt-in only (explicit "clean remotes too" / --include-remote):
git push origin --delete <branch>                      # only for merged-pr remotes
```

The link that keeps `-D` safe: delete with `-D` **only** for branches
`hygiene_gather.py` classified `merged-pr` (its PR/MR state is *merged*). For
`closed-unmerged`, `stale`, or `no-pr` branches, the work may be unsaved — never
`-D` them on the strength of the sweep; require an explicit per-branch go-ahead,
and if a guarded delete fails, surface it rather than escalating to `-D`.

Pass `--include-remote` / run `git push origin --delete` only when the user
explicitly asked to clean remotes — local-only is the default.

Report the outcome per item (`closed` / `deleted` / `FAILED` + reason).

## Safety guarantees (inherited + enforced here)

- **Report-first:** no PR closed, no branch deleted without a confirmed action.
- **Scope:** act only on items shown in the stale/prunable sections of the report
  the user just saw — never expand scope between report and action.
- **Force-delete is evidence-gated:** `git branch -D` is used *only* on branches
  whose PR/MR state is verified `merged`. Unmerged / closed-unmerged / no-PR
  branches are never force-deleted on the strength of the sweep.
- **Protected/current are untouchable:** the default branch, protected globs, and
  the current branch are never deleted (both `branch_clean.sh` and
  `hygiene_gather.py` mark them).
- **Remote deletion is opt-in** (`--include-remote` / explicit request only).
- **Auth/CLI failures are surfaced** (`errors` array), never reported as "clean".

## Notes

- Bot-PR floods (many near-identical Jules/Copilot/Palette PRs) are better
  handled by `pr-triage-bots` — if the queue is dominated by bot duplicates, point
  the user there for blob-level dedup before this general sweep.
- Issue backlog hygiene is a separate concern — see `issue-prioritize` /
  `issue-triage`.

## Sub-agent dispatch

When ≥3 open PRs or stale branches exist, dispatch one sub-agent per PR/branch batch to assess disposition, then
consolidate; below that, sweep inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `manifest parallel-agent` /
inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.
