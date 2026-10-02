# Sub-Agent Dispatch & Selection Rules

> Read-on-demand reference. Skills that dispatch work link here rather than
> restating these rules.

## OMP-native dispatch

OMP `task` and `hub` are the only interactive sub-agent contract. When work has
independent units, the parent dispatches all ready units in **one** `task` call,
in waves of at most 32. Each task states its bounded unit, acceptance criteria,
and read/write scope.

Choose the narrowest role:

| Work | `task` agent |
|---|---|
| Read-only exploration, inventory, or research | `scout` |
| Quality, correctness, or maintainability review | `reviewer` |
| Security review | `security-reviewer` |
| Strictly mechanical collection or updates | `sonic` |
| Implementation or mixed work | Omit `agent` for the default worker |

Children execute their assigned unit directly and **never redispatch**. Use
`hub` only to coordinate or wait for already-dispatched workers. The parent
validates results, resolves material disagreements from evidence, and aggregates
the final outcome.

If `task` is unavailable, perform the units inline and report `DEGRADED`. Never
fall back to a provider CLI for interactive fan-out.

## Workload decomposition

Fanning out independent units is workload decomposition; requesting a second
opinion on one artifact is review. Dispatch genuinely independent units when
doing so reduces latency or separates non-overlapping work. A numeric threshold in an owning skill's
`subagent_trigger` is a workload-decomposition rule, not an independent-review
trigger. Counts of files, packages, modules, languages, keywords, or units are
decomposition signals only and never trigger independent review.

Independent review and cross-verification follow the five-condition risk gate
in `orchestration.md`: trust-boundary change, destructive behavior, broad
compatibility or deployment change, conflicting evidence or unresolved
uncertainty, or a codebase-wide investigation with genuinely independent
tracks. Skills whose fan-out is decomposition rather than review — `docs-all`,
`docs-improve`, `issue-prioritize` — stay outside that gate.

A skill records one disposition in `configs/claude/config/command_config.yml`:

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

### Enforcement

`tests/bats/subagent_policy.bats` enumerates the disposition from
`config/command_config.yml`: every skill carries a `subagents` value, every
`conditional` entry names a `subagent_trigger`, every `never` entry gives a
`subagent_rationale`, dispatching skills link a selection-reference contract
from their `## Sub-agent dispatch` section, and the retired coordinator
settings (`parallel_agents`, `subagent_model`, `session_model`,
`harness_routing`, `consensus`, and their siblings) are rejected anywhere in
the tree. Model choice is therefore stated at the dispatch site, not pinned in
configuration:

| Model | Use for |
|---|---|
| `sonnet` | **The default.** Any dispatch that is not one of the rows below. |
| `haiku` | Purely mechanical fan-out: file reads, greps, per-item transforms. |
| `opus` | Genuinely hard reasoning — adversarial verification of security or correctness findings. |
| `charter` | Per-role tiers declared in the CDDL charters (`cddl-role-models.md`). |

Ad-hoc dispatches outside a skill (scout, general-purpose, one-off fan-out) are
not reachable by that gate, so the same default is stated as a rule in the
always-loaded orchestration guides' Token Economy section.

## Skill authoring convention

```yaml
tool_policies:
  <skill-name>:
    subagents: conditional
    subagent_trigger: "independent analysis tracks with no shared state"
```

`conditional` entries require `subagent_trigger`; `never` entries require a
one-line `subagent_rationale`. Dispatching skills include a `## Sub-agent
dispatch` section that names the units, links this reference, and says that
children do not redispatch and the parent validates and aggregates results.

### Verify

```bash
bats tests/bats/subagent_policy.bats
yamllint configs/claude/config/command_config.yml
```
