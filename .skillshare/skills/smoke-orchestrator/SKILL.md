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

## Install (opt-in runtime deps)

UI/API steps need Playwright + Chromium; CLI steps and the appender need neither.

```bash
python3 -m pip install -r tests/requirements-smoke.txt
python3 -m playwright install chromium
```
