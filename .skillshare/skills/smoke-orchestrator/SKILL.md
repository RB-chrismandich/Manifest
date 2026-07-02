---
name: smoke-orchestrator
description: Append, run, and maintain declarative tiered E2E smoke tests (UI/API/CLI) per app. Use after shipping a feature to add coverage, to gate a PR (Lite run → JUnit + exit code), or for nightly Full runs. Catalog lives in smoke-catalog/<app>.yaml.
---

# Smoke Orchestrator

Declarative, config-driven E2E smoke tests an agent can author and run. A
per-app YAML catalog (`smoke-catalog/<app>.yaml`) holds tiered, chainable tests
spanning three step types — **UI** (Playwright), **API/HTTP**, and **CLI/shell** —
so multi-language targets are reachable by one engine. The engine lives in
`configs/claude/scripts/smoke_orchestrator/`; drive it via
`configs/claude/scripts/smoke_test.py` (deployed: `~/.claude/scripts/smoke_test.py`).

Trigger phrases: "add a smoke test", "smoke-test this feature", "gate the PR with
a Lite run", "run the nightly smoke suite", "what smoke coverage exists".

## When to append (after shipping a feature)

Right after building a user-facing workflow, describe it as a structured
workflow description and append it — coverage grows in lockstep with the product.

```bash
echo '{
  "app": "billing", "id": "create-and-view-invoice", "tier": "Lite",
  "title": "Create an invoice via API, then view it in the UI",
  "steps": [
    {"name":"create","type":"api","method":"POST","path":"/api/invoices",
     "body":{"amount":100},"expect_status":201,"captures":{"invoice_id":"$.id"}},
    {"name":"view","type":"ui","action":"goto",
     "value":"/invoices/${state.invoice_id}","needs":["invoice_id"]}
  ]
}' | ~/.claude/scripts/smoke_test.py append --stdin
```

Append is **idempotent by `id`** (re-appending updates in place; FR-004) and
**validated before any write** (invalid input leaves the catalog untouched).
Add `--dry-run` to validate and preview without writing.

## Tiers (cumulative)

`Lite` ⊆ `Full` ⊆ `Full+Extra`. Tag a test once at its lowest applicable tier;
a broader run is a superset. Use `Lite` for the fast critical-path PR gate,
`Full` for nightly, `Full+Extra` for edge cases.

## How to run (the gate)

> **cwd contract**: run from the project root — the catalog root defaults to the
> RELATIVE `./smoke-catalog` (it is not deployed to any home). From anywhere
> else, pass `--catalog-dir /path/to/project/smoke-catalog` explicitly.

```bash
# PR gate — fast critical path. exit 0 = merge-safe; 1 = a test failed/blocked; 2 = empty/usage.
~/.claude/scripts/smoke_test.py run --app billing --tier Lite --junit smoke-lite.xml

# Nightly — cumulative Lite + Full.
~/.claude/scripts/smoke_test.py run --app billing --tier Full --junit smoke-full.xml
```

The runner emits **JUnit XML** (CI annotations) + a console summary; the **exit
code is the gate**. An empty selection (no tests matched the tier) is reported
distinctly (exit 2), never as a false pass.

## Chaining, state, and secrets

- A step `captures:` named outputs (`$.json.path` for api, a selector for ui, a
  regex group for cli); a downstream step `needs:` them. Missing upstream state
  → the step is **blocked** (never run with a missing value, never a false pass).
- References resolve at run time: `${state.<name>}` (captured this run / persisted)
  and `${env.<NAME>}` (environment).
- **Secrets are env-injected and never persisted.** Mark a step `sensitive: true`;
  its values resolve only from `${env.*}`, are redacted from every output sink,
  and are never written to the catalog or persisted state. A sensitive ref with
  no env source fails clearly (no plaintext fallback).

## Lifecycle

```bash
~/.claude/scripts/smoke_test.py list --app billing            # coverage: id, tier, step count
~/.claude/scripts/smoke_test.py list --json                   # machine-readable, all apps
~/.claude/scripts/smoke_test.py prune --app billing --id old-test   # idempotent remove-by-id
```

## Safety

- CLI steps are **argument arrays only** (never a shell string); resolved state
  lands in discrete argv elements, so a captured value can never inject a command.
- Every step runs under a bounded timeout. There is **no automatic retry** by
  default; opt in per step with `retry: {attempts: N}` for eventually-consistent
  steps only.

## AI-driven UI steps (`mode: agent`)

A UI step can run in two modes. The default, `mode: deterministic`, uses
Playwright selectors (`goto`/`click`/`fill`/`expect_*`). `mode: agent` instead
lets **browser-use** (an LLM) drive the browser from a natural-language `task`,
judged against `judge_context` — selectorless and resilient to DOM churn (this
subsumes the legacy `browser-test` skill).

```yaml
- name: login
  type: ui
  mode: agent
  task: "Log in as the demo user and confirm the dashboard loads"
  judge_context: ["user reaches the dashboard after login"]
  url: /login          # optional; defaults to catalog base_url
  max_steps: 15        # optional
```

**Safety rule:** agent steps are LLM-judged and non-deterministic, so they **may
not be tier `Lite`** — the PR gate stays deterministic. Put them in `Full` /
`Full+Extra`. Captures are best-effort: if browser-use can't surface a declared
value it's omitted, so any downstream `needs` is blocked (never a silent run).
Playwright and browser-use use **separate browser contexts** — chain across the
two engines by value (`captures`/`needs`), not shared cookies.

Migrate existing `browser-test` prompts into a catalog:

```bash
python3 -m smoke_orchestrator.migrate tests/browser --app <app>   # → smoke-catalog/<app>.yaml (tier Full)
```

## Install (opt-in runtime deps)

Deterministic UI/API steps need Playwright + Chromium; CLI steps and the appender
need neither. `mode: agent` steps additionally need browser-use + an LLM key.

```bash
python3 -m pip install -r tests/requirements-smoke.txt
python3 -m playwright install chromium
# only if using mode: agent steps:
python3 -m pip install -r tests/requirements-smoke-agent.txt   # + export OPENAI_API_KEY
```
