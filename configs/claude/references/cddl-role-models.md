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

At invoke time (`Task` sub-agent **or** `cddl_invoke.py`), map a retained
noninteractive provider tier through `~/.claude/config/model_policy.yml`:

```text
model_tiers.<provider>.<tier>  →  provider-native model name
```

Examples (see repository `model_policy.yml` for authoritative pins):

| Tier | Claude | Cursor | Antigravity |
|------|--------|--------|-------------|
| Security | opus | advanced | advanced |
| Review | sonnet | flash | flash |
| Light | haiku | mini | flash |

Never hardcode provider model strings in charter bodies. Update
`model_tiers.<provider>.*` in `model_policy.yml` when a provider renames a
model, then run bootstrap to deploy the policy.
