# Quickstart: Adding (or declining) sub-agent guidance to a skill

This is the design-phase source for the durable convention (FR-013). At implementation time it is
authored into the single location — `configs/claude/references/sub-agent-dispatch.md` (read-on-demand,
indexed from `configs/claude/CLAUDE.md`), beneath the shared "Sub-Agent Selection Rules" (SC-007).
Follow it when adding a new skill or auditing an existing one.

## 1. Classify the skill

Ask: **does this skill's work decompose into independent units?**

| Answer | `subagents` | Example |
|--------|-------------|---------|
| Decomposition IS the job (always fan out) | `always` | `docs-all` (one sub-agent per docs skill) |
| Only above a threshold | `conditional` | `refactor-python` (≥3 independent modules) |
| Single-step / sequential / mutates shared state | `never` | `checkpoint`, `token-economy` |

## 2. Record it in the canonical store

Edit `configs/claude/config/command_config.yml` under `tool_policies.<skill-name>`:

```yaml
  <skill-name>:
    subagents: conditional
    subagent_trigger: "independent_units >= 3"     # only when conditional
```

For `never`, add a one-line `subagent_rationale:` (or a `# comment` in the SKILL.md body).

## 3. Add the in-body trigger (only for always / conditional)

In the skill's `SKILL.md` **body** (not frontmatter), per
[contracts/skill-trigger.format.md](./contracts/skill-trigger.format.md):

```markdown
## Sub-agent dispatch

When ≥3 independent <units> exist, dispatch one sub-agent per <unit> to <task>, then merge.
Below that, do it inline. Pick the mechanism per the shared **Sub-Agent Selection Rules** in the
selection-rules reference (`configs/claude/references/sub-agent-dispatch.md`).
Sub-agents execute directly and do not re-dispatch.
```

## 4. Do NOT restate the selection rules

Native Task sub-agents vs. `parallel_agent.py`, and the cross-platform fallback, live ONCE in
`configs/claude/references/sub-agent-dispatch.md` → "Sub-Agent Selection Rules". Link to it; never copy it.

## 5. Verify

```bash
bats tests/bats/subagent_policy.bats        # coverage + consistency gate
yamllint configs/claude/config/command_config.yml
```

A new skill with no `subagents` disposition will FAIL the test until you classify it — that is the
intended forcing function.

## Mechanism cheat-sheet (summary of the shared rules)

- **Parallel reads / research / fan-out audit** → native **Task sub-agents** (Claude). On non-Claude
  assistants, run inline or use `parallel_agent.py`.
- **Independent cross-model verification** of a security-sensitive / architectural / >200-line change
  → **`parallel_agent.py`** (cross-platform; satisfies the constitution's Tier-1 gate).
- **Trivial / single-unit / <3 independent items** → **inline**, no dispatch.
