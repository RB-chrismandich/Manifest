# Phase 1 Data Model: Sub-Agent Dispatch Guidance

This feature has no runtime data store. The "data model" is the config schema extension plus the
structural shape of the guidance artifacts.

## Entity: Skill Policy Entry (`tool_policies.<skill-name>`)

One YAML mapping per skill under `tool_policies` in `command_config.yml`. **Existing** fields are
unchanged; **new** fields are added by this feature.

| Field | Status | Type | Values / Rule |
|-------|--------|------|---------------|
| `allowed` | existing | list | Tool names the skill may use |
| `forbidden` | existing | list | Tool names the skill may not use |
| `parallel_agents` | existing | enum | `always` \| `conditional` \| `never` \| `gate-only` — governs **external** `parallel_agent.py` |
| `trigger_condition` | existing | string | Scale expr for `parallel_agents: conditional` (e.g., `total_doc_lines >= 500`) |
| `validation_tier` | existing | int | `1` \| `2` |
| `subagents` | **NEW** | enum | `always` \| `conditional` \| `never` — governs **native Task/Agent** sub-agents |
| `subagent_trigger` | **NEW** | string | Required iff `subagents: conditional`. Checkable expr, default floor `independent_units >= 3` |
| `subagent_rationale` | **NEW (optional)** | string | One-line why for `subagents: never` (may instead live as a SKILL.md comment) |

### Validation rules

- **VR-1**: Every skill directory with a `SKILL.md` MUST have a `tool_policies` entry with a
  `subagents` value. (Coverage — SC-001)
- **VR-2**: `subagents: conditional` ⇒ `subagent_trigger` present and non-empty.
- **VR-3**: `subagents: never` ⇒ a rationale exists (in `subagent_rationale` or the SKILL.md body).
- **VR-4**: `subagents: always|conditional` ⇒ the SKILL.md body contains a concrete dispatch trigger
  that references the shared selection rules.
- **VR-5**: A skill's prose trigger MUST NOT contradict its `subagents` value (e.g., a body that
  says "dispatch one agent per X" while `subagents: never`). (Consistency — SC-004)
- **VR-6**: `subagent_trigger` thresholds default to `>= 3` independent units unless an existing
  per-skill scale threshold applies.

### Disposition state (per skill)

```text
never  ──(work decomposes into ≥3 independent units, OR scale threshold)──▶ conditional
conditional ──(decomposition is the skill's core job, e.g. docs-all)──▶ always
```
No runtime transitions; this is a one-time classification recorded in config.

## Entity: Dispatch Trigger (in `SKILL.md` body)

- **Where**: skill body (NOT frontmatter — frontmatter is auto-loaded; bodies are not).
- **Shape**: a directive, checkable sentence + a link to the shared selection rules.
- **Required parts**: condition (count/size/independence) · mechanism pointer · per-agent task ·
  no-recursion note (inherited from shared rules).

## Entity: Shared Selection Rules (in `configs/claude/references/sub-agent-dispatch.md`)

- **Single instance** (read-on-demand reference, indexed from `configs/claude/CLAUDE.md`), referenced
  by all dispatching skills.
- **Contents**: native Task sub-agents vs `parallel_agent.py` decision logic; cross-platform
  fallback; no-recursion rule; the ≥3-unit default floor.

## Entity: Enforcement Test

- **Where**: `tests/bats/subagent_policy.bats` (or `tests/python/test_subagent_policy.py`).
- **Inputs**: the live `.retired skill supply/skills/` directory listing + parsed `tool_policies`.
- **Asserts**: VR-1 … VR-5 (VR-6 advisory). Counts skills dynamically.

## Relationships

```text
Skill (SKILL.md) ──1:1── Skill Policy Entry (tool_policies.<skill>)
Skill Policy Entry ──refers to──▶ Shared Selection Rules (CLAUDE.md)  [for always|conditional]
Dispatch Trigger (in body) ──must agree with──▶ subagents value       [VR-5]
Enforcement Test ──verifies──▶ all of the above
```
