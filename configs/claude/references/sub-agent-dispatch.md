# Sub-Agent Dispatch & Selection Rules

> Read-on-demand reference (NOT auto-loaded). Skills that fan work out link here instead of
> restating these rules. Indexed from `configs/claude/CLAUDE.md` → "Reference Index".

This repo has **two** sub-agent paradigms. A skill's `tool_policies` entry in
`config/command_config.yml` records which it uses (`subagents` and/or `parallel_agents`); the skill
body states the concrete trigger and links here.

## The two mechanisms

| Mechanism | What it is | Use for | Availability |
|-----------|-----------|---------|--------------|
| **Native Task/Agent sub-agents** | In-session sub-agents dispatched via the Task tool (Explore, general-purpose, …) | Parallel reads, fan-out research, independent per-item work, broad audits, **CDDL personas** | **Claude Code, Cursor** |
| **`parallel_agent.py`** | External multi-CLI cross-verification (Gemini/Cursor/Codex/Antigravity) with consensus scoring | Independent cross-model verification of one artifact/decision | Cross-platform |
| **Headless CLI invoke** (`cddl_invoke.py`, `EVOLVE_CLI`, `SYNTH_CLI`) | Single-provider subprocess using `cli_agents` config | CDDL critics on Gemini/Codex/Agy; synthesis; SkillClaw evolve | Cross-platform (CLI on PATH) |

## Selection rules (by task type)

| Task type | Mechanism | Notes |
|-----------|-----------|-------|
| Parallel information-gathering / research / broad audit (many independent items) | Native Task sub-agents | One sub-agent per item/batch. On Gemini/Codex/Agy → `parallel_agent.py` or inline. |
| CDDL personas (`/spec-implement-loop`) | Task sub-agents on Claude/Cursor; else `cddl_invoke.py` | See skill `prompts/cli-dispatch.md`. Developer writes only in main session when Task absent. |
| Independent cross-model verification of a security-sensitive, architectural, or >200-line change | `parallel_agent.py` | Required by the constitution's Tier-1 gate (Principle II). Not native sub-agents. |
| Trivial / single-unit / fewer than the threshold | **Inline** | No dispatch — overhead is not justified. |

## When to dispatch (the threshold)

Dispatch only when **≥3 independent units of work** exist, OR an existing per-skill scale threshold
is exceeded (e.g., `total_doc_lines >= 500`, `unique_imports >= 5`). Below that, do the work inline.
This default keeps token-conserve intact; the structured value lives in each skill's
`subagent_trigger` in `command_config.yml` (authoritative), and the skill body's prose must agree.

## Model selection (measured — the one cache-safe cost lever)

**Default a dispatched sub-agent to Sonnet unless the task needs more.** Pass an
explicit `model` when dispatching; do not inherit the parent's model by accident.

Measured 2026-07-25 over 47,185 real API requests
(`docs/baselines/2026-07-25-credit-baseline.md`): 63% of sub-agent traffic
already runs Sonnet, but the premium remainder costs **$845** more than it needs
to — Opus sub-agents $503.74→$302.24, Fable sub-agents $919.32→$275.80. Fable is
the bigger half: it bills $10/$50 per MTok, 2x Opus.

Sub-agents are the **only** place a model switch is cache-safe, because each
carries its own context and its own cache. That is what makes this lever work
and the obvious alternative fail:

> **Do not route individual turns within a conversation to a cheaper model.**
> Prompt caches are model-scoped. Main-loop turns average ~150K cache-read
> tokens, so switching model mid-conversation invalidates the prefix and forces
> the next premium turn to pay a full cache **write**. Measured on the most
> attractive candidate class (mechanical tool calls, median output 150 tokens):
> **$129 saved against a $1,628 penalty — net −$1,499.** This is the intuitive
> optimisation and it loses money; it is rejected on evidence, not preference.

Escalate a sub-agent above Sonnet only for genuinely hard reasoning. Mechanical
fan-out (file reads, greps, per-item transforms) is Haiku-eligible and roughly
halves the Sonnet figure again.

## No recursion

A dispatched sub-agent performs its assigned task **directly** and does **not** itself fan out
further sub-agents. This prevents agent-explosion.

## Cross-platform fallback

| Platform | Native Task | Fallback for fan-out / CDDL critics |
|----------|-------------|-------------------------------------|
| Claude Code | Yes | — |
| Cursor | Yes | — |
| Gemini CLI, Codex, Antigravity | No | `cddl_invoke.py`, `parallel_agent.py`, or inline |

Never leave an assistant without an executable path. Headless seams share
`parallel_agent.yml` → `cli_agents` and `SYNTH_*` / `CDDL_INVOKE_*` / `EVOLVE_*` env overrides.

---

## Convention: adding (or declining) sub-agent guidance to a skill

The durable contributor convention (this is the one documented place).

### 1. Classify the skill

| Does the work decompose into independent units? | `subagents` | Example |
|--------------------------------------------------|-------------|---------|
| Decomposition IS the job (always fan out) | `always` | `docs-all` |
| Only above the threshold | `conditional` | `python-refactor` |
| Single-step / sequential / mutates shared state | `never` | `session-checkpoint` |

### 2. Record it in `config/command_config.yml` (canonical store)

```yaml
tool_policies:
  <skill-name>:
    subagents: conditional
    subagent_trigger: "independent_units >= 3"   # only when conditional
    # subagent_rationale: "<one line>"           # when never (or as a SKILL.md note, below)
```

For a `never` skill you may record the rationale either as `subagent_rationale` here **or** as a
one-line marker in the `SKILL.md` body: `> Sub-agents: not used — <reason>.` The enforcement test
accepts either form.

### 3. Add the in-body trigger (always / conditional only)

In the skill's `SKILL.md` **body** (never frontmatter — frontmatter is auto-loaded):

```markdown
## Sub-agent dispatch

When ≥3 independent <units> exist, dispatch one sub-agent per <unit> to <task>, then merge.
Below that, do it inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task on Claude Code/Cursor, or
`parallel_agent.py` / `cddl_invoke.py` / inline on other assistants. Sub-agents execute
directly and do not re-dispatch.
```

### 4. Do NOT restate these rules

Link here; never copy. The selection rules and threshold live once, in this file.

### 5. Verify

```bash
bats tests/bats/subagent_policy.bats        # coverage + consistency gate
yamllint configs/claude/config/command_config.yml
```

A new skill with no `subagents` disposition fails the test until classified — the intended forcing
function.
