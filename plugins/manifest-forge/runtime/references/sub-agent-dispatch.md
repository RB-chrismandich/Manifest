# Native Sub-Agent Dispatch

Use the current host's supported native mechanism. OMP parents batch ready
independent units with `task` and coordinate through `hub`; Claude Code parents
use only discovered native Agent types and background collection. This portable
reference does not define host-specific aliases or a second orchestration
implementation. The deployed host's shared dispatch contract is authoritative
for child limits, the narrow delegate-runner exception, and `DEGRADED` behavior.

## Wire-contract evidence in task briefs

For every cross-process API or wire contract, quote or cite the authoritative
producer source with `file:line`; do not reconstruct a contract from memory.
Fixtures must be producer-derived or captured from real responses. Matching
self-authored fakes alone do not prove compatibility. When a live endpoint is
available and a read-only probe is permitted, run it before claiming verified
integration. If producer or live evidence is unavailable, state that the
behavior is unknown/unverified rather than infer it.

The inventory briefing example's authoritative wire producer is
`src/manifest_agent/models.py:151-188`; its OMP population sites are
`src/manifest_agent/adapters/omp_inspection.py:96-154,187-234,327-379`.
The consumer regression
`tests/python/plugin_runtime/test_reconcile_native_evidence.py` serializes those
producer dataclasses in a fresh process. It does not establish live discovery
or activation. For task-item fields and the session semaphore, read the active
host's `omp://tools/task.md` (Inputs and Limits & Caps); its current settings,
not documentation defaults, determine the active concurrency bound.

Before an OMP reviewer wave, read the active `omp://tools/task.md` and inspect
`omp config list`. Dispatch structured reviewer results only when
`task.structured` is enabled and the actual native `task` tool contract exposes
both per-item `outputSchema` and `schemaMode`; documentation or prompt text
alone does not establish that the current tool accepts those fields. If either
capability is absent, do not send unsupported fields or substitute a
prompt-only contract: perform parent-only validation and mark the reviewer
result `DEGRADED`.

For each review unit, attach its exact output schema to that task item and
select strict schema mode. For example, a duplicate-pair reviewer item is:

```json
{
  "name": "duplicate-42-43-reviewer-1",
  "agent": "reviewer",
  "task": "Review only the assigned pair; return its duplicate verdict.",
  "solutionSpace": "read-only verdict against the assigned pair",
  "outputSchema": {
    "type": "object",
    "required": ["is_duplicate", "confidence", "reasoning"],
    "additionalProperties": false,
    "properties": {
      "is_duplicate": {"type": "boolean"},
      "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
      "reasoning": {"type": "string"}
    }
  },
  "schemaMode": "strict"
}
```

Use a distinct stable `name` for every candidate/reviewer slot and preserve
submission order, including failed or invalid results. Bound each submitted
wave to `min(32, task.maxConcurrency)` when the configured limit is positive;
when it is `0` (unlimited), retain the 32-item wave ceiling. If the active
limit cannot be read or validated, do not submit an unknown-sized wave and
mark the operation `DEGRADED`.
