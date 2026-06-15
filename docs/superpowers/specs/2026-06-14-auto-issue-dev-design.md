# Design: Autonomous Issue Developer (`/auto-issue-dev`)

**Date**: 2026-06-14
**Status**: Approved (design); pending implementation plan
**Author**: Claude Code (with chrismandich)

---

## Problem

The repo has the building blocks of an issue → code → close pipeline
(`/issue-prioritize` for selection, the #345 issue-linking hooks for status
sync and `Closes #N`, TDD/verify skills for development) but nothing wires them
into a single unattended invocation. The goal is a curated, fully autonomous
loop that picks an opted-in issue, develops it test-first, and opens a PR for
human review — repeating until the queue is empty.

## Goals

- One invocation that develops **one** opted-in issue end-to-end and stops at
  **PR-open** (never merges).
- Unattended looping over the whole eligible queue via the existing `/loop`
  skill, with **fresh context per issue** (no single-session context bloat).
- Safe by default: only touches issues the user has explicitly labeled.
- Fail-open and non-destructive to unrelated work.

## Non-Goals

- Auto-merging PRs (explicitly out — stop at PR-open).
- Reimplementing status-sync or `Closes #N` (delegated to the #345 hooks).
- Parallel/fan-out development (rejected approach C — risky for unattended PRs).
- Issue selection scoring beyond what `/issue-prioritize` already provides.

## Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| Eligibility | **Opt-in label only** — issue must carry `auto-dev`. |
| Failure handling | **Draft PR + `needs-human` label + explanatory comment, then continue** ("3+1"). |
| Stop condition | **Queue empty** — no remaining *ready* open `auto-dev` issues. |
| Merge policy | **Stop at PR-open** — human reviews and merges. |
| Autonomy | **Fully autonomous loop** via `/loop /auto-issue-dev`. |
| Dependency handling | If an issue declares an **unmet dependency** (a referenced issue/PR that is not yet closed/merged), **do not develop it**: label `blocked-dependency`, comment naming the unmet ref(s), and **exclude it from loop scope**. |

## Approach (B): thin selection helper + markdown orchestration + `/loop`

A small deterministic, testable shell helper handles issue selection and the
failure-flag mutation. The SKILL.md orchestrates development of a single issue
per invocation. `/loop` re-invokes the skill with fresh context until the
helper reports the queue is empty.

```
/loop /auto-issue-dev
   └─ per iteration (fresh context):
        auto_issue_dev.sh next-issue        # returns first READY auto-dev issue
          │  (internally, per candidate oldest-first:)
          │    check-deps <N> → unmet?  → label blocked-dependency + comment, skip candidate
          │    ready?                   → return JSON
          └─ no ready candidate         → exit 3 (queue empty → loop ends)
        git switch -c <N>-slug              # numeric prefix links #N (#345 hooks)
        test-driven-development             # write failing test → implement → green
        /verify                             # lint + test + scan
        ├─ success → gh pr create           # #345 hook adds "Closes #N", issue→needs-review
        └─ failure → gh pr create --draft   # no Closes keyword
                     auto_issue_dev.sh mark-blocked <N> "<reason>"   # needs-human + comment
```

## Components

### 1. `configs/claude/scripts/auto_issue_dev.sh`

Platform-agnostic (wraps `git_ops.sh` / `git_platform.sh`). Conventions per
`.claude/CLAUDE.md`: `err()` for all error/warning output, `--help` (≤15 lines,
exit 0).

| Subcommand | Behavior | Exit |
|------------|----------|------|
| `next-issue [--json]` | Walk open `auto-dev` issues oldest-first; for each, run the `check-deps` logic — if unmet, tag `blocked-dependency` + comment and skip; return the **first ready** candidate. (Score-ordering via `/issue-prioritize` deferred to a later iteration; v1 = oldest-first for determinism.) Exit-0 JSON: `{number,title,url,skipped_dependency}`. Exit-3 JSON (queue empty): `{ready:0,skipped_dependency:N,skipped_other:M}` so the caller can report counts despite fresh per-iteration context. | `0` with ready candidate; **`3` when no ready candidate** (queue empty); `1` on hard error |
| `check-deps <N> [--json]` | Parse issue #N's body/title for dependency refs (`depends on #M`, `blocked by #M`, `requires #M`, `needs #M`, case-insensitive); resolve each via `git_ops.sh`. Print unmet refs (open issues / unmerged PRs). | `0` all met; **`2` unmet deps found**; `1` on hard error |
| `mark-blocked <N> <reason>` | Add `needs-human` label to #N + one deduped comment (marker `<!-- auto-issue-dev:blocked -->`) explaining the reason. Fail-open. | `0` always |
| `mark-dependency <N> <refs>` | Add `blocked-dependency` label to #N + one deduped comment (marker `<!-- auto-issue-dev:dependency -->`) naming the unmet ref(s). Fail-open. | `0` always |
| `--help` | Usage + subcommands. | `0` |

Testing seams (env overrides, mirroring `issue_support.sh`): `GIT_OPS_BIN`,
`GIT_PLATFORM_BIN`, `AUTO_ISSUE_DEV_LABEL` (default `auto-dev`),
`AUTO_ISSUE_DEV_DEP_LABEL` (default `blocked-dependency`).

### 2. `.skillshare/skills/auto-issue-dev/SKILL.md`

Per-invocation procedure (one issue):

1. **Preflight**: ensure issue hooks enabled (`install_issue_hooks.sh --enable`
   if the runtime gate is off); confirm `gh`/`glab` authed.
2. **Select**: run `auto_issue_dev.sh next-issue --json` — this already skips and
   tags dependency-blocked candidates, returning the first ready issue. **Exit 3
   ⇒ announce "eligible queue empty — stopping" and end** (this is how `/loop`
   terminates); read the exit-3 JSON (`skipped_dependency`, `skipped_other`) to
   report in the final summary how many were skipped — the count comes from the
   helper, not skill-side accumulation (each iteration is fresh context).
3. **Branch**: `git switch -c <N>-<slug>` (numeric prefix → #345 resolves #N).
4. **Develop**: invoke `test-driven-development` — failing test first, then
   minimal implementation, scoped to the issue.
5. **Verify**: run `/verify`; treat lint warn as non-blocking, test/security
   fail as blocking.
6. **Branch on outcome**:
   - **Success** → `gh pr create` (real PR). The #345 PR hook injects
     `Closes #N` and moves the issue to `needs-review`. **Stop — do not merge.**
   - **Failure / stuck** → `gh pr create --draft` (no closing keyword) +
     `auto_issue_dev.sh mark-blocked <N> "<why>"`. Continue (loop picks next).
7. Return a one-line outcome summary for the loop log.

Includes a `Critical Rules` block: never merge; never touch issues lacking
`auto-dev`; one issue per invocation; on failure push partial work as a **draft**
PR (no `Closes` keyword) so a human can inspect it — never as a real PR.

### 3. `configs/cursor/rules/auto-issue-dev.mdc`

Cross-tool parity stub (per #345 convention; Gemini/Codex/Antigravity inherit
via symlinked skills).

### 4. Labels (`configs/claude/config/labels.yml` + `label_sync.sh`)

Add three canonical labels:

- `auto-dev` — opt-in gate; "Eligible for the autonomous issue developer."
- `needs-human` — failure flag; "Auto-dev could not complete; needs a human."
- `blocked-dependency` — dependency flag; "Has an unmet dependency; excluded from
  the auto-dev loop until the blocking issue/PR merges." Filterable so a human
  can see the whole dependency-blocked backlog at a glance.

Colors chosen distinct from the existing six; provisioned via existing
`label_sync.sh` across GitHub/GitLab/Linear.

### 4a. Dependency detection

A candidate issue is **not ready** if it declares a dependency that is not yet
satisfied. Detection (v1) is **keyword-based** on the issue body/title — the
conventional, platform-portable approach (GitHub's native "blocked by"
relationships have inconsistent CLI/API coverage across GitHub/GitLab/Linear):

- Recognized patterns (case-insensitive): `depends on #M`, `blocked by #M`,
  `requires #M`, `needs #M` — `M` is an issue or PR number, possibly a list.
- Each ref `M` is resolved via `git_ops.sh`: **met** if the referenced issue is
  closed or the referenced PR is merged; **unmet** otherwise (open / unmerged).
- Any unmet ref ⇒ the candidate is skipped, tagged `blocked-dependency`, and a
  deduped comment names the unmet ref(s). The loop never develops it.
- Self-references and already-`blocked-dependency` issues are skipped cheaply.

Already-tagged `blocked-dependency` issues are excluded from `next-issue` up
front; the tag is re-evaluated only when the user removes it (e.g. after the
blocker merges), keeping the loop from re-commenting every pass.

### 5. Wiring

- `configs/claude/config/command_config.yml` → `tool_policies.auto-issue-dev`
  (`allowed: [Bash, Read, Edit, Write]`, since this skill writes code).
- `docs/COMMANDS.md` → entry under the autonomous/issue section.
- `.skillshare/skills/auto-issue-dev/evals/evals.json` → triggering evals.

## Error Handling

- Helper is **fail-open**: `mark-blocked` and tracker outages never abort; they
  warn via `err()` and exit 0. `next-issue` distinguishes *empty queue* (exit 3,
  normal loop end) from *hard error* (exit 1).
- On dev/verify failure the skill **never opens a real (non-draft) PR**: the
  work-in-progress is pushed as a **draft** instead, so half-finished changes
  are visible for a human but carry no `Closes #N` keyword and don't advance the
  issue to `needs-review`. (If there are literally no commits to push, skip the
  draft and only `mark-blocked`.)
- All status-sync failures are already fail-open in the #345 engine.

## Testing

- `tests/bats/auto_issue_dev.bats`: selection ordering, label filtering,
  empty-queue → exit 3, **dependency detection** (met/unmet ref parsing,
  candidate skip + `blocked-dependency` tag, already-tagged exclusion,
  `check-deps` exit 2), `mark-blocked`/`mark-dependency` dedup + fail-open,
  `--help`, error routing through `err()`.
- `shellcheck configs/claude/scripts/auto_issue_dev.sh`.
- `yamllint` on `labels.yml` and `command_config.yml`.
- Skill evals (triggering accuracy).
- Manual e2e (sandbox/throwaway issues, mirroring the issue-closer e2e): one
  `auto-dev` issue → run skill → real PR with `Closes #N`; one deliberately
  unbuildable issue → draft PR + `needs-human`; one issue with `blocked by #X`
  where #X is open → skipped + `blocked-dependency` tag + comment.

## Open Questions

- **Dependency detection mechanism**: v1 uses keyword parsing (`depends on #M`,
  `blocked by #M`, `requires #M`, `needs #M`) for platform portability. If you'd
  rather rely on GitHub's native "blocked by" relationships (GitHub-only, via
  GraphQL), that's a v2 swap behind the same `check-deps` interface.
