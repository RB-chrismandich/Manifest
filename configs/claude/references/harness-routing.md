# Runtime Harness Handling

Read before writing or modifying skills or agents that run under more than one
harness. Interactive dispatch is current-host native; do not hardcode provider
commands or model identifiers in portable skill guidance.

## Interactive dispatch contract

The [shared dispatch contract](sub-agent-dispatch.md) is authoritative.

- OMP parents batch ready independent units with `task` and coordinate with
  `hub`; select its documented specialist roles.
- Claude Code parents use only discovered native Agent types and native
  background-agent collection.
- Portable skills link the shared contract instead of restating host branches.
- Cursor, Gemini, Codex, Antigravity, Devin, and other hosts gain no native API
  from this contract. Their existing guidance remains authoritative.

## Rules

1. Keep skill frontmatter to `name` and `description`; harness-specific metadata
   in frontmatter is configuration drift.
2. Record a skill's `subagents`, optional `subagent_trigger`, and
   `subagent_rationale` in `config/command_config.yml`.
3. Put harness differences in the live harness guides, not in each skill.
4. Noninteractive single-provider routing is governed separately by
   `model_policy.yml`; it is not an interactive orchestration mechanism.
