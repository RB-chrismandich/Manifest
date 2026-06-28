# CLI Contract: `smoke_test.py`

Entry point: `configs/claude/scripts/smoke_test.py` (also `python -m smoke_orchestrator`). Every subcommand handles `--help` before any dependency/config lookup and exits 0 (repo convention).

## `smoke_test.py append`

Adds or updates one test from a workflow description (the agent-facing "test appender").

| Arg | Required | Description |
|-----|----------|-------------|
| `--from <file.json>` | one of | Path to a workflow description (validated vs `workflow-description.schema.json`). |
| `--stdin` | one of | Read the workflow description JSON from stdin (hook-friendly). |
| `--catalog-dir <dir>` | no | Catalog root (default: `smoke-catalog/`). |
| `--dry-run` | no | Validate + show the diff; write nothing. |

**Behavior**: validate → upsert by `id` (idempotent) → atomic write under per-app `flock`.
**Exit**: `0` appended/updated; `2` validation error (catalog unchanged); `1` I/O error.

## `smoke_test.py run`

Executes the catalog filtered by tier (the executor / gate).

| Arg | Required | Description |
|-----|----------|-------------|
| `--app <name>` | no | Run one app's catalog; omit to run all. |
| `--tier <Lite\|Full\|Full+Extra>` | no | Cumulative selection (default `Lite`). |
| `--junit <path>` | no | Write JUnit XML (default: `./smoke-report.xml`). |
| `--base-url <url>` | no | Override catalog `base_url`. |
| `--persist-state` | no | Enable cross-run persisted (non-secret) state. |

**Behavior**: select cumulatively → order chained steps → resolve `${state.*}`/`${env.*}` (secret-safe) → run under per-step timeout (no auto-retry unless declared) → emit JUnit XML + console summary.
**Exit**: `0` all selected passed; `1` ≥1 failed/blocked; `2` empty selection (no tests matched) or usage error.

## `smoke_test.py list`

Reports coverage without executing (FR-014).

| Arg | Required | Description |
|-----|----------|-------------|
| `--app <name>` | no | Limit to one app. |
| `--json` | no | Machine-readable output. |

**Output**: per workflow `id`, `tier`, step count. **Exit**: `0`.

## `smoke_test.py prune`

Removes a test from a catalog by identifier (FR-018).

| Arg | Required | Description |
|-----|----------|-------------|
| `--app <name>` | yes | Catalog file to edit. |
| `--id <id>` | yes | Test identifier to remove. |

**Behavior**: under per-app `flock`, remove the test if present; absent id is a no-op. Atomic write. **Exit**: `0` removed or already-absent (idempotent); `1` I/O error.

## Programmatic API (library)

```python
from smoke_orchestrator.appender import SmokeTestAppender
from smoke_orchestrator.executor import SmokeTestExecutor

SmokeTestAppender(catalog_dir="smoke-catalog").append(workflow_description)   # idempotent upsert
report = SmokeTestExecutor(catalog_dir="smoke-catalog").run(app="billing", tier="Lite")
assert report.exit_code == 0
```
