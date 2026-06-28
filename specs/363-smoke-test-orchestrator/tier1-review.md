# Tier-1 Security Cross-Verification (T038)

Constitution II/III gate for the smoke-test orchestrator (security-sensitive:
CLI/shell execution + secret handling). Run via `parallel_agent.py` on the
attack surface: `steps/cli.py`, `steps/api.py`, `state.py`, `redact.py`,
`executor.py`, `report.py`.

**Agents**: claude ✅, antigravity ✅, gemini ❌ (auth failure —
`IneligibleTierError`, free-tier client deprecated; environment issue, not code).
2 independent agents completed → meets the ≥2 Tier-1 minimum. Consensus 8/10.

## Findings & resolutions

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| A | — | Shell/command injection | **CLEAN** (both agents): `subprocess.run` is `shell=False` with an arg-array; resolved `${...}` lands in discrete argv elements. No change. |
| 1 | HIGH | Uncaught runner exception aborts the run **and** dumps a traceback containing the resolved step (with substituted secrets) to stderr | Defensive `except Exception` in `executor._dispatch` → `StepOutcome(False, "unexpected <Type> during <step>")` (type only, no content); broadened `cli.py` to `except OSError`; `api.py` non-JSON body → `CaptureError`. Run now always completes (FR-011) and no traceback escapes. |
| 2 | HIGH | `_test_status([])` returns `passed` → false-pass on zero steps | Guard `if not steps: return "failed"` (defense-in-depth; `validate_catalog` already rejects empty steps upstream). |
| 3 | MED | Persisted state files world-readable at default umask | `_write_persisted` sets dir `0o700`, file `0o600`. |
| 4 | MED | `${state.*}` refs not registered with the redactor inside a `sensitive` step (only `${env.*}` were) | Register both kinds when the step is `sensitive`. |

**Not adopted**: antigravity's "auto-register *all* `${env.*}` values regardless
of the `sensitive` flag" — over-masks non-secret env vars (e.g. `HOME`/`PATH`) in
reports and contradicts the spec's flag-based model (FR-013). The defensive
exception catch (#1) closes the actual leak vector (traceback exposure) instead.

All resolutions are regression-tested (4 new cases:
`test_empty_steps_never_passes`, `test_runner_oserror_fails_step_without_aborting_run`,
`test_unexpected_runner_exception_is_contained_and_not_leaked`,
`test_sensitive_state_ref_is_redacted`). Post-fix verdict: **APPROVED**.
