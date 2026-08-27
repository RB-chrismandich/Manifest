# Parallel Orchestration Contract

The skill runs the installed harness CLIs already present on `PATH`. It never
installs a harness, imports the ephemeral coordinator, or resolves files outside
its own skill root. Immutable configuration and prompt assets are adjacent to
the entry point; mutable output belongs below
`$XDG_STATE_HOME/manifest/agent-outputs/`.

## Structured result

JSON output preserves the orchestration schema used by existing consumers:

- `timestamp`, `mode`, and `prompt`
- `agents.<provider>.{status,model,output,error,duration_seconds}`
- `cross_verification.{consensus_score,confidence,agent_count}`
- `validation.{tier1,tier2,verdict}` when validation is requested
- `output_files` for bundle-owned XDG artifacts

Unavailable harnesses are skipped with an explicit diagnostic. If fewer than
the recommended number are available, the result remains structured and the
warning is advisory. If none are available, the command exits non-zero.

## Cross-domain use

Invoke `manifest-workspace:parallel-agent` with target files, mode, validation flag, and
timeout. Consume its JSON result when the harness supports structured skill
output; otherwise perform the same review inline and report `DEGRADED`.

Invoke `manifest-workspace:learning-capture` with category, language, and finding text
when a reusable lesson emerges. Failure to capture learning is advisory and
must not change the primary verdict.
