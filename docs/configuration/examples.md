# Configuration Examples

> Common OMP dispatch and single-provider model-policy configurations.

**Last Updated**: 2026-09-12

## OMP dispatch

A skill declares whether it can use OMP task batches in
`command_config.yml`:

```yaml
tool_policies:
  issue-triage:
    subagents: conditional
    subagent_trigger: independent_units >= 3
```

When the condition applies, the parent defines independent units and their
result schema, sends all ready units in one `task` call (at most 32 per wave),
and validates the returned evidence. Mutations remain sequential. If `task` is
unavailable, execute inline and report `DEGRADED`.

## Noninteractive model policy

`model_policy.yml` controls retained single-provider integrations:

```yaml
provider_order: [antigravity, cursor, gemini, codex, claude, devin]
model_tiers:
  codex:
    advanced: gpt-5.6-sol
    flash: gpt-5.6-terra
    mini: gpt-5.6-luna
model_fallback:
  mode: confirm
  chains:
    codex: [advanced, flash, mini, auto]
credit_fallback:
  codex: [advanced, flash, mini]
timeouts:
  default: 120
```

The integration resolves one CLI route and sends its prompt through stdin. It
never serves as an interactive fallback for OMP task dispatch.

---

[← Configuration](README.md)
