# CDDL role model tiers (cross-platform)

Role charters under `configs/claude/prompts/cddl/*.md` declare a **tier alias**
in frontmatter, not a provider-specific model id:

```yaml
---
name: qa-critic
model: sonnet
---
```

## Resolution

At invoke time (Task sub-agent **or** `cddl_invoke.py`), map the tier through
`~/.claude/config/parallel_agent.yml`:

```text
model_tiers.<provider>.<tier>  →  provider-native model name
```

Examples (see repo `parallel_agent.yml` for authoritative pins):

| Tier | Claude | Cursor | Antigravity |
|------|--------|--------|-------------|
| `sonnet` | claude-sonnet-4-6 | (cursor tier) | Claude Sonnet 4.6 (Thinking) |
| `flash` | … | … | Gemini 3.5 Flash (High) |
| `opus` | … | … | Claude Opus 4.6 (Thinking) |

## Editing tiers

1. Change `model:` in the role charter (semantic tier only).
2. Adjust `model_tiers.<provider>.*` when a provider renames models.
3. `./bootstrap.sh` to redeploy prompts; config ships via `parallel_agent.yml`.

Never hardcode provider model strings in charter bodies — keeps the same roles
portable across Claude, Cursor, Antigravity, Gemini, and Codex CLIs.
