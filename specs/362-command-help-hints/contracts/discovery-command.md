# Contract: Discovery Command (`/help`)

Interactive in-session discovery surface (skill `.retired skill supply/skills/help/`). Read-only.

## Invocation

```text
/help [query] [--category <key>] [--all]
```

| Arg | Type | Meaning |
|-----|------|---------|
| `query` | free text (optional) | Intent/keyword search across name, category, description, when-to-use. |
| `--category <key>` | enum (optional) | Restrict to one taxonomy category. |
| `--all` | flag | Include `unavailable` commands (default: hide, or show greyed with reason). |
| `--limit <N>` | int (optional) | Cap rows shown (default cap applies even when omitted). |

## Behavior contract

- **Empty `query` + no `--category`** → full listing grouped by category (`order` asc, `uncategorized` last). Each row: `name` · one-line `description` · `when_to_use`.
- **`query` present** → ranked matches (name > category > description/when-to-use; ties alphabetical).
- **No match** → explicit `No command matches "<query>".` (never a misleading suggestion). [Edge case]
- **Unavailable commands** → marked with `reason` (FR-008); never recommended as the top result.
- **Deterministic & offline** → no model call; identical input → identical output (testable, SC-001/SC-003).
- **Bounded output** → results are capped at a default row limit (override with `--limit`); when truncated, a footer `… N more — narrow with /help <query>` is shown rather than dumping the full ~84-command list into one turn (spec edge case "context-budget pressure"). Per-category grouping headers are always shown so the user can re-query.
- **Output is one-shot** → not injected into always-loaded context (FR-009).

## Outputs

Grouped Markdown to the session. Each category header shows `label`; each entry is
`` `/name` — description _(when to use)_ ``. Unavailable entries suffixed `— unavailable: <reason>`.

## Acceptance hooks

- Maps to spec US1 scenarios 1–3, SC-001.
- `--help` path MUST succeed before any catalog/config load (repo `cli-help-before-dependency-checks` convention).
