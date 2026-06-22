# Contract: Machine Catalog Schema

Intermediate representation emitted by `command_catalog.py --json`. Consumed by the doc
renderer, the discovery skill, and the hint emitter. Not committed (regenerated on demand).

## Schema

```json
{
  "generated_for_platform": "claude",
  "categories": [
    { "key": "git-pr", "label": "Git & PRs", "order": 1 }
  ],
  "commands": [
    {
      "name": "branch-clean",
      "description": "Identify and safely prune stale git branches …",
      "when_to_use": "Use when pruning merged, gone, or stale branches",
      "category": "git-pr",
      "availability": {
        "service_enabled": true,
        "deployed_to_platform": true,
        "status": "available",
        "reason": null
      }
    }
  ]
}
```

## Field rules

| Field | Constraint |
|-------|-----------|
| `commands[].name` | unique kebab-case; primary key |
| `commands[].description` | non-empty; verbatim from frontmatter |
| `commands[].when_to_use` | derived (D2); never empty (falls back to humanized name) |
| `commands[].category` | ∈ `categories[].key` ∪ `"uncategorized"` |
| `commands[].availability.status` | `available` \| `unavailable` |
| `categories[]` | closed set from `command_categories.yml`; stable `order` |

## Stability contract

- Ordering is deterministic: categories by `order`, commands alphabetical within category.
- Output is a pure function of (skill sources, `command_categories.yml`, `services.yml`, platform) — enabling the drift-check and reproducible tests.
