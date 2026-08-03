# Runtime Harness Handling

Read before writing or modifying skills/agents that run under more than one
harness. Routing is centralized — never hardcode model IDs or per-harness
config in SKILL.md/agent frontmatter.

## Authoritative config

| Concern | Source of truth |
|---------|-----------------|
| Per-harness execution semantics + default tier | `~/.claude/config/command_config.yml` → `harness_routing` |
| Verified model ID pins per harness | `~/.claude/config/parallel_agent.yml` → `model_tiers` |
| Per-skill Claude sub-agent/session models | `~/.claude/config/command_config.yml` → `tool_policies` |

## Per-harness execution semantics

- **Claude Code (`claude`)**: native tool signatures (`Read`, `Edit`, `Grep`,
  `Bash`) and sub-agent dispatch per `tool_policies` (sub-agents pinned Sonnet
  by default; never inherit the session's model).
- **Codex (`codex`)**: direct shell execution; format output as standard
  unified diffs. Model default is `auto` (account default) — pins are
  login-gated and unverified.
- **Cursor (`cursor`)**: follow workspace context constraints; apply edits
  directly to files.
- **Antigravity (`agy`)**: execute via the standard agent context wrapper.
  Ships no guide of its own (provider, not orchestrator); reads `AGENTS.md`.

## Rules

1. Model IDs live only in `parallel_agent.yml` `model_tiers` (verified pins,
   dated probes). Reference tiers by name (`sonnet`, `flash`, `advanced`).
2. Skill frontmatter stays `name` + `description` — always-loaded context is
   budget-gated (`tests/bats/context_budget.bats`); per-file harness metadata
   is drift, not configuration.
3. Cross-harness behavior differences belong in the harness's own guide
   (`CLAUDE.md`, `AGENTS.md`, `orchestration.mdc`), not duplicated per skill.
