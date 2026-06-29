# Contract: Health-Check Reporting

**Surface**: `configs/claude/scripts/check_status.sh` and the `/health-check` skill.

## Reported items

When graphify is enabled in `services.yml`, `check_status.sh` MUST report:

| Check | Output (normal) | Output (gap) |
|-------|-----------------|--------------|
| Enabled | reported as a managed **tool** under CLI Tools (NOT counted in "Enabled Services (N/5)" nor `working_agents` — graphify is not a consensus agent, D4) | shown as `○ Graphify (disabled)` when off |
| CLI installed | `✓ Graphify CLI installed` (+ version/backend in verbose) | `○ Graphify CLI not installed` + install hint |
| Backend/auth | `host-agent (no key required)` | only if an optional backend (e.g. `GEMINI_API_KEY`) is selected but unset → actionable note |

## Rules

- Detection via `command -v graphify`; version via `graphify --version 2>/dev/null || echo unknown`.
- Default backend is host-agent ⇒ "unauthenticated" is NOT an error state by default; auth is reported N/A unless a backend key path is configured.
- Reporting MUST be non-fatal: a missing graphify never makes `check_status.sh` exit non-zero on its own.

## States (SC-004)

In scope for this feature (default local-first config):
1. enabled-and-ready → enabled ✓ + installed ✓
2. enabled-but-not-installed → enabled ✓ + not-installed ○ + hint

Deferred (out of baseline scope — only if optional enriched backends are added later):
3. enabled-but-unauthenticated → enabled ✓ + installed ✓ + backend key missing. No detection/test in this feature.
