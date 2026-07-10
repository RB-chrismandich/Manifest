# Contract: Role-Agent File Frontmatter + Body

**Surface**: `configs/claude/agents/<name>.md` (six files) → deployed to `~/.claude/agents/`.
Consumer: Claude Code's native agent loader + the orchestrator following the delegation policy.

## Frontmatter (YAML)

```yaml
---
name: <role-name>          # one of: scout | Explore | mech-executor | executor | verifier | security-executor
description: <when to delegate to this role — trigger text the orchestrator reads>
model: <built-in alias>    # one of: haiku | sonnet | opus  (a built-in Claude Code alias, NOT a custom
                           # name and NOT a raw model ID — FR-002; Claude Code resolves these natively)
effort: <low|medium|high>
---
```

## Per-role binding (normative)

| File | `model` (built-in alias) | `effort` | Body responsibility |
|------|--------------------------|----------|---------------------|
| `scout.md` | `haiku` | `low` | Read-only lookups / symbol searches; returns findings only, no edits. |
| `Explore.md` | `haiku` | `low` | Search-override for the built-in search agent; read-only. |
| `mech-executor.md` | `sonnet` | `low` | Fully-specified mechanical work (pattern refactors, convention tests, docs, bulk edits). |
| `executor.md` | `opus` | `medium` | Judgment work (features, bug fixes). |
| `verifier.md` | `opus` | `medium` | Fresh-context adversarial check; MUST return a `CONFIRMED` or `REFUTED` verdict. |
| `security-executor.md` | `opus` | `high` | Security-sensitive work; MUST NOT be downgraded to `sonnet`/`haiku` (FR-004). |

## Invariants (testable)

- **INV-1**: Exactly six files exist; filename stem == frontmatter `name` (case-sensitive). Note
  `Explore` is **deliberately capital-E** to match Claude Code's built-in `Explore` search agent
  **exactly** (the built-in is capitalized `Explore`, confirmed against the Claude Code agent-type
  registry), so the override binds on case-sensitive filesystems (Linux) too — a lowercase
  `explore.md` would NOT override it there.
- **INV-2**: `model` is a built-in Claude Code alias (`haiku`/`sonnet`/`opus`), never a literal
  model ID (grep: no `claude-` string in any agent frontmatter `model:` field) — unless a
  documented per-role pin override is intentionally used (FR-002).
- **INV-3**: `security-executor` `model: opus`; `Explore` and `scout` `model: haiku`.
- **INV-4**: `verifier.md` body specifies the CONFIRMED/REFUTED return contract.
- **INV-5**: No agent file names another assistant home in its body policy.
