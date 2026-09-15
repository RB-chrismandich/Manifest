# Contract: `tool_policies` subagents extension

**Applies to**: every `tool_policies.<skill-name>` mapping in
`configs/claude/config/command_config.yml`.

## New fields

```yaml
tool_policies:
  <skill-name>:
    # ── existing fields (unchanged) ──
    allowed: [ ... ]
    forbidden: [ ... ]
    retired_cross_harness_coordinator_policy: always | conditional | never | gate-only   # external the retired cross-harness coordinator
    trigger_condition: "<expr>"        # only when retired_cross_harness_coordinator_policy: conditional
    validation_tier: 1 | 2

    # ── new in feature 367 ──
    subagents: always | conditional | never        # REQUIRED for every skill — native Task sub-agents
    subagent_trigger: "<expr>"                      # REQUIRED iff subagents == conditional
    subagent_rationale: "<one line>"               # OPTIONAL; for subagents == never (or in SKILL.md)
```

## Field rules

- `subagents` — **required, enum**. `always` = decomposition is the skill's core job (e.g.,
  `docs-all`). `conditional` = fan out only above a threshold. `never` = single-step / inherently
  sequential / mutating-shared-state.
- `subagent_trigger` — **required when `conditional`**, else omitted. A checkable expression. Default
  floor `independent_units >= 3`; may reuse an existing scale gate (`total_doc_lines >= 500`,
  `unique_imports >= 5`).
- `subagent_rationale` — present (here or as a `# comment` in the SKILL.md body) when `never`.

## Examples

```yaml
  docs-all:
    subagents: always               # orchestrates docs-readme/diagrams/improve as sub-agents

  refactor-python:
    subagents: conditional
    subagent_trigger: "independent_modules >= 3"

  checkpoint:
    subagents: never
    subagent_rationale: "single-session summarization; no independent units to fan out"
```

## Backward compatibility

- Additive only — no existing field is renamed or removed.
- `parallel_agents` keeps its current meaning (external harness); `subagents` is orthogonal.
- A skill MAY be `retired_cross_harness_coordinator_policy: never` while `subagents: conditional` (different mechanisms,
  different purposes).
