# /spec-review — Gemini Cross-Reference of Project Artifacts — Design

> An analysis-only Manifest skill that cross-references spec / plan / tasks
> artifacts for consistency using the `gemini` CLI, and surfaces structured
> remediation guidance. On-demand plus an optional fail-open save hook.

**Date**: 2026-06-08
**Status**: Approved (design) — pending implementation plan
**Audience**: Manifest maintainers

---

## Problem

When a feature is specified across multiple artifacts (a spec, a plan, and a task
list), the artifacts drift: the plan promises something the tasks contradict, the
spec defines a constraint the plan violates. Catching this by hand is tedious and
easy to skip. We want an automated, independent cross-check that reads the
artifacts and reports inconsistencies with a concrete remediation path.

An independent **second model** (Gemini) is the valuable signal here, because the
artifacts are usually authored by Claude — having a different model review them
catches blind spots that Claude-reviewing-Claude would miss.

## Decisions (resolved during brainstorming)

| Decision | Choice |
|----------|--------|
| Packaging | A **new Manifest skill** (`/spec-review`), NOT a new `agi`/Antigravity CLI. Antigravity is an IDE in this repo (symlink-only config dir); there is no `agi` binary to extend. |
| Reviewer engine | **Gemini alone** via the `gemini` CLI (`gemini -p`). Uses existing CLI auth — no Google API key, no client library, no model pinning to a dated `1.5 Flash`. |
| Trigger | **On-demand `/spec-review`** (primary) **plus an optional Claude Code PostToolUse save hook** (advisory, debounced, fail-open). NOT a background daemon / file-watcher. |
| Framework scope | **Framework-agnostic**: speckit (`spec.md`/`plan.md`/`tasks.md`) and superpowers (`*-design.md` + plan-with-embedded-tasks). |
| Mutation | **Analysis-only.** Never edits artifacts (like `speckit-analyze`, `pr-review`). |
| Name / output | Skill `/spec-review`; silent-mode findings → `.spec-review/feedback.md` (gitignored). |

## Non-Goals

- No `agi` CLI / sub-command framework (does not exist; out of scope for a
  bash/Python/YAML config repo).
- No background daemon or file-system watcher (the SkillClaw lesson: inline
  daemons are fragile and rate-limit-prone).
- No multi-model consensus in V1 (Gemini-only; `parallel_agent.py` is a possible
  future engine swap, see Follow-ups).
- No auto-editing / auto-fixing of artifacts.

## Relationship to existing tooling

- **`speckit-analyze`** (vendored github-spec-kit skill) already does cross-artifact
  consistency — but it is speckit-only (`requires .specify/`), third-party/vendored
  (editing it drifts from upstream), and Claude-driven. `/spec-review` is
  Manifest-owned, **framework-agnostic**, and uses an **independent model**
  (Gemini). They are complementary, not duplicative.
- **`gemini` CLI** is already installed and authenticated; we shell out to it
  exactly as SkillClaw shells to `claude -p`.

---

## Architecture

One core engine script, two thin entry points:

```text
┌─ /spec-review  (SKILL.md, on-demand) ──┐
│                                         ├─►  spec_review.sh  ─►  gemini -p <prompt>  ─►  findings
└─ PostToolUse hook (settings.json) ──────┘     discover → assemble → invoke → parse → format
   (auto on Write/Edit to artifact paths,
    debounced + fail-open + --silent)
```

## Components

### New

- **`configs/claude/scripts/spec_review.sh`** — the engine.
  - **Flags:** `--spec FILE --plan FILE --tasks FILE` (explicit) OR auto-discover;
    `--silent` (hook mode); `--format tree|json` (default `tree`).
  - **Discovery (framework-agnostic):**
    - *speckit:* `.specify/` or `specs/<NNN>-*/{spec,plan,tasks}.md`.
    - *superpowers:* `docs/superpowers/specs/*-design.md` (spec) +
      `docs/superpowers/plans/*.md` (plan, **with tasks embedded** — there is no
      separate `tasks.md`). The cross-reference for superpowers is therefore
      **spec ↔ plan(+embedded tasks)**; for speckit it is the three-way
      **spec ↔ plan ↔ tasks**. The assembled prompt states which shape it sees.
  - **Engine seam:** `gemini` is invoked through one function with an injectable
    override (`SPEC_REVIEW_GEMINI`, default `gemini`), so tests never touch the
    network or the user's Gemini quota.
  - **Debounce (silent/hook mode):** a per-project cooldown file
    (`.spec-review/.last-run`); skip if it ran within `cooldown_seconds`
    (default 60) **and** skip when fewer than 2 artifacts exist (a lone file
    cannot be cross-referenced). Bounds `gemini` call frequency with no daemon.
  - **Analysis-only:** reads artifacts; never writes to them.

- **`configs/claude/prompts/spec_review.md`** — the distillation/critique prompt
  template. Instructs Gemini to cross-reference the supplied artifacts and emit
  each inconsistency in the exact `Location / The Gap / Recommended Direction /
  Reason Why` structure, or a single `NO_ISSUES` token when consistent.
  Version-controlled, deployed to `~/.claude/prompts/`.

- **`.skillshare/skills/spec-review/SKILL.md`** — the on-demand `/spec-review`
  entry point. Frontmatter (`name`, `description`); body instructs Claude to run
  `spec_review.sh` (auto-discover or with explicit paths) and present the findings.

- **PostToolUse hook** — registered in `configs/claude/settings.local.json` (which
  deploys to `~/.claude/settings.json` and already contains a `hooks` block), under
  a `PostToolUse` matcher for `Write|Edit`. The hook command runs
  `spec_review.sh --silent`, which itself filters to artifact paths (spec/plan/tasks
  globs) and applies debounce — so the matcher stays broad and the script owns the
  path logic. **Advisory and non-blocking.**

- **`.gitignore`** — add `.spec-review/` so silent-mode `feedback.md` and the
  `.last-run` cooldown file are never committed.

### Output format

Structured tree to stdout (the agreed shape):

```text
[spec-review] Cross-referencing project artifacts with Gemini…

⚠️  CLARIFICATION REQUIRED: <short title>
   ├─ Location: <artifact A> vs <artifact B>
   ├─ The Gap: <one-sentence description of the inconsistency>
   ├─ Recommended Direction: <concrete remediation, may be multi-step>
   └─ Reason Why: <why it matters / which constraint it violates>
```

- `--format json` emits the same findings as a JSON array for machine use.
- No issues → `✓ No inconsistencies found across N artifacts.` and exit 0.

## Error handling & fail-open

The hard lesson from SkillClaw — **a review tool must never block or break the
user's primary work**:

- **PostToolUse hook is advisory and non-blocking.** It never rejects or delays a
  Write/Edit. On any failure it degrades quietly.
- **`gemini` missing / unauthenticated / non-zero exit:** silent mode logs a single
  line and writes nothing harmful (exit 0); on-demand mode surfaces a clear,
  actionable error (e.g. "gemini CLI not found / not logged in").
- **Malformed Gemini output:** degrade gracefully — print the raw response under a
  warning rather than crashing; never partial-write a corrupt `feedback.md`.
- **No artifacts found:** `nothing to review`, exit 0.
- **Silent mode** writes findings to `.spec-review/feedback.md` and prints one
  summary line; `.spec-review/` is gitignored.

## Testing

- **bats `spec_review.bats`:**
  - speckit-layout discovery; superpowers-layout discovery (spec + plan with
    embedded tasks); no-artifacts case → clean exit.
  - debounce: cooldown skip (ran < `cooldown_seconds` ago); `<2`-artifacts skip.
  - `gemini` mocked via the `SPEC_REVIEW_GEMINI` seam (a stub script) → no network.
  - tree formatting of a representative finding; `--format json` shape.
  - `--silent` writes `.spec-review/feedback.md` and prints one line.
  - malformed-Gemini-output tolerance (no crash, no corrupt feedback file).
  - hook fail-open: non-zero gemini in `--silent` mode → exit 0.
- **shellcheck** clean on `spec_review.sh`.
- **markdownlint** on `SKILL.md` + `spec_review.md`; **settings.json** validates as
  JSON.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Save hook fires `gemini` too often (cost/rate limits) | Debounce cooldown file + `<2`-artifact skip; hook is opt-in |
| Hook blocks or breaks the user's Write/Edit | Advisory/non-blocking by construction; fail-open on every error path |
| `gemini` not authed in headless/CI | Silent mode exits 0 with a logged note; on-demand gives a clear message |
| Gemini returns non-structured prose | Tolerant parse: show raw under a warning, never crash |
| Superpowers "tasks" mis-discovered as a missing file | Discovery treats plan-with-embedded-tasks as the canonical superpowers shape |

## Follow-ups (not in V1)

- **Pluggable engine** — swap `gemini -p` for `parallel_agent.py` multi-model
  consensus behind the existing engine seam.
- **`git` pre-commit hook** variant for teams that prefer commit-time over
  save-time checks.
- **Auto-fix mode** — offer to apply the `Recommended Direction` (kept out of V1;
  analysis-only by design).

---

## Related Documents

- [speckit-analyze skill](../../../.claude/skills/speckit-analyze/SKILL.md) — the
  speckit-only cross-artifact analyzer this complements
- [docs/SKILLCLAW.md](../../SKILLCLAW.md) — the `claude -p` / fail-open / engine-seam
  patterns reused here
