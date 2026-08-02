# CDDL role model tiers (cross-platform)

Role charters under `runtime/prompts/cddl/*.md` declare a **tier alias**
in frontmatter, not a provider-specific model id:

```yaml
---
name: qa-critic
model: sonnet
---
```

## Resolution

At invoke time (Task sub-agent **or** `cddl_invoke.py`), map the tier through
adjacent `runtime/config/review_models.json`:

```text
model_tiers.<provider>.<tier>  →  provider-native model name
```

Examples (see repo `review_models.json` for authoritative pins):

| Tier | Claude | Cursor | Antigravity |
|------|--------|--------|-------------|
| `sonnet` | claude-sonnet-4-6 | (cursor tier) | Claude Sonnet 4.6 (Thinking) |
| `flash` | … | … | Gemini 3.5 Flash (High) |
| `opus` | … | … | Claude Opus 4.6 (Thinking) |

## Editing tiers

1. Change `model:` in the role charter (semantic tier only).
2. Adjust `model_tiers.<provider>.*` when a provider renames models.
3. regenerate and verify the bundle-local JSON config.

Never hardcode provider model strings in charter bodies — keeps the same roles
portable across Claude, Cursor, Antigravity, Gemini, and Codex CLIs.
