# Command Configuration

> OMP dispatch policy, allowed tools, and validation tiers by skill.

**Last Updated**: 2026-09-12

## Command Configuration

**File**: `~/.claude/config/command_config.yml`

Each `tool_policies` entry records the tools a skill may use, its validation tier,
and OMP dispatch policy:

```yaml
tool_policies:
  python-refactor:
    allowed: [Read, Glob, Grep, Bash]
    forbidden: [Write, Edit]
    validation_tier: 1
    subagents: conditional
    subagent_trigger: review_risk_condition
    subagent_rationale: Independent review only for material risk or uncertainty.

  docs-generate-diagrams:
    allowed: [Read, Glob, Grep, Bash]
    validation_tier: 2
    subagents: conditional
    subagent_trigger: unique_imports >= 5
```

`subagents` is `always`, `conditional`, or `never`. For `always` and triggered
`conditional` policies, submit all ready independent units in one OMP `task`
call (at most 32 per wave). Children do not redispatch; the parent validates and
aggregates evidence, with `hub` used only for coordination or waiting. If OMP is
unavailable, execute inline and report `DEGRADED`.

## Single-provider model policy

**File**: `~/.claude/config/model_policy.yml`

This policy serves noninteractive integrations only. It keeps `provider_order`,
`model_tiers`, `model_fallback`, `credit_fallback`, `timeouts.default`, and
`cli_agents` command shapes. A caller resolves one provider route, writes the
prompt to stdin, and applies bounded output and timeout handling. It does not
dispatch interactive sub-agents or synthesize their text.

## Validation tiers

**File**: `~/.claude/config/validation_criteria.yml`

Tier 1 is blocking for security, error handling, and breaking changes. Tier 2
is advisory for bugs, performance, maintainability, and tests. Command-specific
overrides select which concerns apply; the parent remains responsible for its
final decision.

Independent review is risk-based: a skill's `conditional_tier1_checks` add
cross-verification only for a confirmed risk condition, never for a file,
module, or unit count.

---

[← Configuration](README.md)
