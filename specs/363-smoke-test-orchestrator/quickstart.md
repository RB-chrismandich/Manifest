# Quickstart: Smoke Test Orchestrator

End-to-end walkthrough of the declarative schema, the tiered/chained example, and the engine boilerplate. This is design-reference for `/speckit-tasks` → `/speckit-implement`, not yet-shipped code.

## 1. Declarative catalog (chained + tiered + state) — `smoke-catalog/billing.yaml`

```yaml
version: 1
app: billing
base_url: https://billing.staging.example.com

tests:
  # Lite = critical path; runs in PR gate AND (cumulatively) in Full / Full+Extra.
  - id: create-and-view-invoice
    title: Create an invoice via API, then view it in the UI
    tier: Lite
    steps:
      - name: login
        type: api
        method: POST
        path: /api/login
        body: { user: "smoke@example.com", token: "${env.BILLING_TOKEN}" }   # secret: env-only
        expect_status: 200
        captures: { session: "$.session_id" }
        sensitive: true                                                       # never persisted/logged

      - name: create_invoice
        type: api
        method: POST
        path: /api/invoices
        body: { amount: 100 }
        expect_status: 201
        needs: [session]
        captures: { invoice_id: "$.id" }                                     # downstream state

      - name: view_invoice
        type: ui
        action: goto
        value: /invoices/${state.invoice_id}                                 # chained from upstream
        needs: [invoice_id]

      - name: assert_amount
        type: ui
        action: expect_text
        selector: "[data-test=amount]"
        value: "$100.00"

  # Full = comprehensive nightly (only runs at Full and above).
  - id: invoice-pdf-export
    title: Export an invoice to PDF via the CLI tool
    tier: Full
    steps:
      - name: export
        type: cli
        command: ["billing-cli", "export", "--id", "${state.invoice_id}", "--fmt", "pdf"]  # arg array
        needs: [invoice_id]
        expect_exit: 0
        timeout_ms: 30000

  # Full+Extra = edge case; opt-in retry for an eventually-consistent webhook.
  - id: webhook-delivery
    title: Verify the payment webhook is eventually delivered
    tier: Full+Extra
    steps:
      - name: poll_webhook
        type: api
        method: GET
        path: /api/webhooks/last
        expect_status: 200
        retry: { attempts: 5 }            # opt-in only; default is no retry
        timeout_ms: 5000
```

## 2. Lifecycle commands

```bash
# Agent appends a new test right after shipping a feature (idempotent by id):
echo '{"app":"billing","id":"create-and-view-invoice","tier":"Lite","steps":[...]}' \
  | configs/claude/scripts/smoke_test.py append --stdin

# PR gate — fast critical path:
configs/claude/scripts/smoke_test.py run --app billing --tier Lite --junit smoke-lite.xml
#   exit 0 = safe to merge; 1 = a Lite test failed/blocked; 2 = no Lite tests matched

# Nightly — comprehensive (cumulatively includes Lite + Full):
configs/claude/scripts/smoke_test.py run --app billing --tier Full --junit smoke-full.xml

# Coverage inspection, no execution:
configs/claude/scripts/smoke_test.py list --app billing
```

## 3. Engine boilerplate (design reference)

```python
# appender.py
class SmokeTestAppender:
    """Idempotently add/update one test in a per-app YAML catalog."""
    def __init__(self, catalog_dir: str = "smoke-catalog") -> None:
        self.catalog_dir = catalog_dir

    def append(self, workflow: dict) -> "AppendResult":
        validate(workflow, WORKFLOW_SCHEMA)          # FR-003: invalid -> raise, no mutation
        path = self._path_for(workflow["app"])       # smoke-catalog/<app>.yaml
        with _file_lock(path):                        # FR-015: per-app flock
            catalog = _load_or_init(path, app=workflow["app"])
            _upsert_by_id(catalog["tests"], _to_test(workflow))   # FR-004: update in place
            _atomic_write(path, catalog)              # tempfile + os.replace
        return AppendResult(id=workflow["id"], updated=...)
```

```python
# executor.py
class SmokeTestExecutor:
    """Run a catalog filtered by tier, chaining state between steps."""
    TIER_RANK = {"Lite": 0, "Full": 1, "Full+Extra": 2}

    def __init__(self, catalog_dir: str = "smoke-catalog", persist_state: bool = False) -> None:
        self.catalog_dir = catalog_dir
        self.state = StateManager(persist=persist_state)   # in-memory + optional persisted
        self.redactor = Redactor()                          # R8: scrub secrets from all output

    def run(self, app: str | None, tier: str = "Lite", junit: str | None = None) -> "RunReport":
        tests = self._select(app, max_rank=self.TIER_RANK[tier])   # FR-006 cumulative
        if not tests:
            return RunReport.empty(tier)                            # FR-008: distinct from pass
        results = []
        with sync_playwright() as pw:                               # shared browser+API context
            ctx = self._make_context(pw)
            for test in tests:
                results.append(self._run_test(test, ctx))
        report = RunReport.build(app, tier, results)
        if junit:
            report.write_junit(junit, redactor=self.redactor)      # R3 JUnit XML
        report.print_summary(redactor=self.redactor)
        return report                                               # report.exit_code drives the gate

    def _run_step(self, step, ctx):
        if not self.state.satisfies(step.get("needs", [])):        # FR-011
            return StepResult.blocked(step["name"])
        resolved = self.state.resolve(step, redactor=self.redactor)  # ${state.*}/${env.*}, R4/R8
        runner = {"ui": run_ui, "api": run_api, "cli": run_cli}[step["type"]]   # R2
        result = with_timeout(step.get("timeout_ms"), step.get("retry"),       # FR-017
                              lambda: runner(resolved, ctx))
        if result.passed and "captures" in step:
            self.state.capture(step["captures"], result, sensitive=step.get("sensitive", False))
        return result
```

```python
# state.py
class StateManager:
    """Named state across steps (in-memory) and runs (persisted, non-secret only)."""
    def __init__(self, persist: bool = False) -> None:
        self._mem: dict[str, object] = {}
        self._persist = persist

    def resolve(self, step: dict, redactor: "Redactor") -> dict:
        # substitute ${state.x} from self._mem and ${env.X} from os.environ;
        # register any ${env.X} flagged sensitive with redactor; raise if a
        # sensitive ref has no env source (FR-013 — no plaintext fallback).
        ...

    def capture(self, captures: dict, result, sensitive: bool) -> None:
        # store extracted values in-memory; if persist and not sensitive,
        # write to $MANIFEST_STATE_ROOT/smoke/state/<app>.json
        ...
```

## 4. Validating the acceptance scenarios

| Spec scenario | Quickstart check |
|---------------|------------------|
| US1 idempotent append (SC-002) | `append` the same `id` twice → one entry; `test_appender.py` |
| US2 cumulative tier + exit code | `run --tier Lite` excludes `Full`; non-zero on failure; `test_executor_tiers.py` |
| US3 chaining + blocked downstream | `view_invoice` gets real `invoice_id`; missing → blocked; `test_chaining_state.py` |
| FR-013 secret safety (SC-006) | `BILLING_TOKEN` never in JUnit/console/state; `test_secret_safety.py` |
