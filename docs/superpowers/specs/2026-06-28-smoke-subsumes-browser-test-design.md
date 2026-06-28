# Smoke Orchestrator Subsumes `browser-test` — Design

**Date**: 2026-06-28
**Status**: Draft (pending approval)
**Topic**: Fold the `browser-test` skill (browser-use, AI-driven UI E2E) into the
smoke-test orchestrator (specs/363) as one more step mode, unifying on a single
catalog, runner, and report — instead of maintaining two parallel E2E systems.

## Context

The repo currently has two end-to-end testing tools with overlapping scope:

- **`browser-test`** — a skill that manages `tests/browser/*.yaml` prompts and runs
  them via [browser-use](https://github.com/browser-use/browser-use). Each test is
  a natural-language `task` with `judge_context` success criteria, executed by an
  **LLM driving a real browser** and graded by an **LLM judge**. UI/browser only.
- **Smoke orchestrator** (specs/363) — a tiered, config-driven runner over a
  per-app YAML catalog (`smoke-catalog/<app>.yaml`). Steps are typed `ui`/`api`/`cli`,
  executed **deterministically** (Playwright selectors, `subprocess`, HTTP) with
  exact assertions, state-chaining (`captures`/`needs`), opt-in `retry`, secret
  redaction, tiering (`Lite`/`Full`/`Full+Extra`), and JUnit XML output.

The smoke orchestrator's *framework* is a strict superset of `browser-test`'s
(tiering, chaining, multi-modal, JUnit, redaction). But the two use **opposite
execution philosophies** — browser-use's selectorless **LLM** flow vs Playwright's
deterministic **selector** flow — so a naive replacement would discard
browser-use's core value (DOM-change resilience, exploratory flows). As of this
writing the smoke orchestrator also has **no consumer** (empty `smoke-catalog/`,
no caller); absorbing `browser-test`'s tests gives it a real one.

### The core tension

| | `browser-test` | smoke orchestrator |
|---|---|---|
| Engine | browser-use (LLM drives the browser from NL `task`) | Playwright (`goto/click/fill/expect_*` on selectors) |
| Pass/fail | LLM judge vs `judge_context` (fuzzy) | exact assertion + exit code (deterministic) |
| Scope | UI/browser only | UI **+ API + CLI** |
| Format | `tests/browser/*.yaml` | `smoke-catalog/<app>.yaml` (typed, tiered, chainable) |
| Extras | auto-trigger on code change; AI test generation | tiering, chaining, JUnit, secret redaction |

### Decisions (locked with user)

1. **Direction** — *subsume*, not replace. Keep both engines; the smoke catalog +
   runner + report become the single framework; browser-use becomes one step mode.
2. **Reject NL→selector translation** — converting each browser-use `task` into
   explicit Playwright steps is lossy and manual; it throws away browser-use's
   selectorless resilience. Not adopted.
3. **Determinism of the gate is preserved** — see the safety rule below.

## Architecture

Add browser-use as a third **UI execution mode** behind the existing executor
dispatch, so it inherits tiering, `retry`, `sensitive` redaction, and JUnit for
free. Existing deterministic UI steps are untouched.

### Catalog schema — new `mode` on `type: ui`

```yaml
# deterministic (existing; mode defaults to "deterministic")
- name: open-home
  type: ui
  action: goto
  value: "/"

# AI-driven (new)
- name: login-and-reach-dashboard
  type: ui
  mode: agent                 # NEW
  task: "Log in as the demo user and confirm the dashboard loads"
  judge_context:              # browser-use's fuzzy success criteria
    - "User reaches the dashboard after login"
  max_steps: 15
```

Schema change: the `type: ui` branch gains an optional `mode` enum
(`deterministic` default, `agent`). When `mode: agent`, `task` is required,
`judge_context` is required (non-empty), `max_steps` is optional (default 15); the
deterministic `action`/`selector`/`value` fields are not used.

### Flow

```text
catalog → validate → select tier → for each step:
    type=api  → steps/api.py        (unchanged)
    type=cli  → steps/cli.py        (unchanged)
    type=ui, mode=deterministic → steps/ui.py     (unchanged, Playwright)
    type=ui, mode=agent         → steps/agent.py  (NEW, browser-use)
        → run task in a browser, LLM-judge vs judge_context → StepOutcome
→ aggregate → JUnit XML + console summary + exit code
```

## Components

### New: `steps/agent.py`

Mirrors `steps/ui.py`'s contract exactly so it drops into the same dispatch:

- Lazy-import `browser_use` (never at module load); absence → clean skip/failure,
  never an import crash (same pattern as Playwright in `ui.py`).
- Run the `task` (bounded by `max_steps` and the step `timeout_ms`).
- Apply the LLM judge against `judge_context` → `StepOutcome(passed, detail)`.
- Any exception/timeout → `StepOutcome(False, ...)` (run never aborts; FR-011).
- Optional `captures` supported if browser-use can surface values; otherwise omit.

### Changed: `executor.py`

One added route: `type == "ui" and mode == "agent"` → `steps/agent.py`; all other
dispatch unchanged. `sensitive` redaction, `retry`, and JUnit reporting apply
uniformly because they live above the per-step runner.

### Changed: schema (`schemas/catalog.schema.json`)

Add the `mode` enum and the `mode: agent` conditional (`task`/`judge_context`
required) under the existing `type: ui` `allOf` branch.

### Skill consolidation

`browser-test`'s genuinely useful behaviors move into the smoke skill as the
**authoring front-end**, now emitting catalog entries instead of
`tests/browser/*.yaml`:

- auto-trigger on new pages / API resolvers / forms (suggest `mode: agent` steps),
- AI generation of tests from a code diff,
- `create` / `list` / `dry-run`.

The smoke runner replaces `browser_test.sh`.

### Migration shim (one-shot)

A ~40-line translator: read `tests/browser/*.yaml` → emit
`smoke-catalog/<app>.yaml` entries with `type: ui, mode: agent`
(`task`→`task`, `judge_context`→`judge_context`, `tags:[smoke]`→`tier: Lite`,
others → `tier: Full`). The two existing templates (`auth-flow.yaml`,
`smoke-test.yaml`) become catalog examples.

## Safety rule (the one that keeps the gate honest)

browser-use brings an **LLM into the gate** — nondeterministic, token-costly, and
graded by a fallible LLM judge. The smoke spec deliberately chose determinism
("no retry by default keeps the gate honest", spec Q5). Therefore:

> **AI (`mode: agent`) steps MUST NOT be tier `Lite`.** `Lite` is the
> PR-blocking gate and must stay deterministic. Agent steps belong in `Full` /
> `Full+Extra` (nightly / exploratory).

Enforced at validation time: a `mode: agent` step in a `Lite`-tagged test is a
catalog validation error. Keep the two graders as distinct modes — never merge
"exact assert" and "LLM judge" into one fuzzy path.

## Dependency reconciliation (loose end to settle first)

The smoke orchestrator already pins Playwright + Chromium (opt-in, in
`tests/requirements-smoke.txt`). browser-use drives its own browser and adds an
LLM client dependency. Decision needed before coding:

- **(preferred)** browser-use as a separate opt-in extra (e.g.
  `requirements-smoke-agent.txt`), installed only when `mode: agent` is used, so
  the deterministic core stays lean; or
- a single combined requirements file (simpler, heavier default footprint).

## Testing

- `steps/agent.py`: unit tests with a **stubbed** browser-use runner (no live
  browser/LLM in CI) — pass path, judge-fail path, missing-dep skip, exception
  containment.
- Schema: accept `mode: agent` with required fields; reject `mode: agent` missing
  `task`/`judge_context`; reject `mode: agent` at tier `Lite`.
- Executor: routes `mode: agent` to the agent runner; `sensitive` redaction still
  applies to agent-step output.
- Migration shim: golden-file test translating the two existing
  `tests/browser/*.yaml` templates → catalog entries.

## Docs / skill

- Update the smoke skill SKILL.md to document `mode: agent` and the authoring
  front-end (absorbing `browser-test`'s create/list/dry-run + auto-trigger).
- Mark `browser-test/SKILL.md` **superseded** → point at smoke; remove
  `browser_test.sh` + the skill after one release (deprecation window).
- Regenerate `docs/COMMANDS.md` + cursor rules; re-check `context_budget.bats`.

## Out of scope

- Rewriting browser-use's internals or its judge model.
- Removing `browser-test` immediately (kept one release as a deprecated alias).
- New step *types* beyond `ui`/`api`/`cli` (agent is a *mode* of `ui`, not a new type).

## Verification

1. Schema validates new/old UI steps; rejects the three error cases above.
2. `pytest tests/python/smoke_orchestrator/` green incl. new agent-runner + shim tests.
3. `bats tests/bats/smoke_orchestrator_cli.bats context_budget.bats` green.
4. Migration shim reproduces the two templates as catalog entries (golden).
5. shellcheck / yamllint / markdownlint / COMMANDS.md + cursor-rule sync clean.
6. End-to-end (manual, needs creds): one `mode: agent` test in tier `Full` runs
   browser-use, is LLM-judged, and emits a JUnit case — and the same catalog's
   deterministic `Lite` steps still gate on exit code.

## Effort

Schema `allOf` branch + `steps/agent.py` + one executor route + skill merge +
~40-line migration script + tests. ~1–2 days. The dependency decision above gates
the start.
