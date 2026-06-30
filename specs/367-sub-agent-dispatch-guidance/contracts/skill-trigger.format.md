# Contract: In-body dispatch trigger (SKILL.md)

**Applies to**: the body of each `SKILL.md` whose `subagents` is `always` or `conditional`.
**Location**: skill **body**, never frontmatter (frontmatter is auto-loaded into context; bodies are
not).

## Required form

A directive, checkable instruction with these parts:

1. **Condition** — a countable/measurable trigger (count, size, independence). Must match the
   `subagent_trigger` in `tool_policies`.
2. **Per-agent task** — what each dispatched sub-agent does.
3. **Mechanism + link** — a pointer to the shared **Sub-Agent Selection Rules** in
   `configs/claude/references/sub-agent-dispatch.md` (do NOT restate the rules).

## Wording rules

- Directive, not advisory: ✅ "When ≥3 independent targets exist, dispatch one sub-agent per target
  to …" ❌ "consider using agents".
- Mention the no-recursion rule by reference (sub-agents execute directly, never re-dispatch).
- `never` skills: a single line such as `> Sub-agents: not used — <reason>.` (no trigger).

## Template snippet (always / conditional)

```markdown
## Sub-agent dispatch

When **<condition, e.g. ≥3 independent modules>**, dispatch **one sub-agent per <unit>** to
**<per-agent task>**, then merge results. Below that threshold, do the work inline.

Choose the mechanism per the shared **Sub-Agent Selection Rules**
(`configs/claude/references/sub-agent-dispatch.md`) — native Task sub-agents vs. `parallel_agent.py`;
cross-platform fallback. Dispatched sub-agents execute their task directly and do not re-dispatch.
```

> **Reference style**: use a deployment-stable *descriptive* pointer to the reference doc, NOT a
> relative markdown link. `SKILL.md` lives three levels deep in source (`.skillshare/skills/<skill>/`)
> and deploys to a different root than the reference (`~/.claude/skills/` vs
> `~/.claude/references/`), so no relative path resolves in both places.

## Consistency contract (verified by the test)

- The body trigger's threshold MUST equal the `subagent_trigger` value in `tool_policies`.
- A body that instructs dispatch MUST NOT belong to a `subagents: never` skill (VR-5).
