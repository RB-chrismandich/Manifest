# Files, Precedence & Environment

> Which configuration source wins for OMP policies and retained model routes.

**Last Updated**: 2026-09-12

## Primary files

- `command_config.yml` — skill tool policies, OMP dispatch policy, triggers, and
  validation tiers.
- `model_policy.yml` — single-provider model tiers, fallback, timeout, and CLI
  invocation policy.
- `validation_criteria.yml` — blocking and advisory validation concerns.
- `services.yml` — installed service state.

For policy loading, an explicit path wins, then the relevant environment
variable, then the deployed configuration path. A malformed required policy is
an error; optional roster data may be absent.

Interactive work follows the OMP guide rather than an environment-selected
provider. If task dispatch is unavailable, the parent executes inline and
reports `DEGRADED`.

---

[← Configuration](README.md)
