# Runtime Harness Handling

Read before writing or modifying skills or agents that run under more than one
harness. Interactive sub-agent dispatch is centralized on OMP; do not hardcode
provider commands or model identifiers in skill guidance.

## Interactive dispatch contract

Every supported interactive harness uses the same OMP contract:

- The parent dispatches independent ready units in one `task` call, in waves of
  at most 32.
- Use `scout` for read-only exploration, `reviewer` for quality review,
  `security-reviewer` for security review, `sonic` only for mechanical work,
  and omit `agent` for default implementation work.
- Children execute directly and never redispatch. `hub` is only for
  coordination and waiting.
- The parent validates and aggregates results.
- If `task` is unavailable, work inline and report `DEGRADED`; never use a
  provider CLI fallback.

## Rules

1. Keep skill frontmatter to `name` and `description`; harness-specific metadata
   in frontmatter is configuration drift.
2. Record a skill's `subagents`, optional `subagent_trigger`, and
   `subagent_rationale` in `config/command_config.yml`.
3. Put harness differences in the live harness guides, not in each skill.
4. Noninteractive single-provider routing is governed separately by
   `model_policy.yml`; it is not an interactive orchestration mechanism.
