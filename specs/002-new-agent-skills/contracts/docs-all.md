# Contract: `docs-all`

**Type**: Claude Code skill (`/docs-all`). Pure sub-agent orchestration — no helper script.

## Invocation

```
/docs-all [<path>] [--order readme,diagrams,improve]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `<path>` | repo root | Scope passed through to sub-skills. |
| `--order` | auto (per-run) | Override the chosen order explicitly. |

## Behavior contract

- **MUST** dispatch `docs-readme`, `docs-diagrams`, `docs-improve` each as an independent sub-agent (Agent tool) (FR-008).
- **MUST** choose order per run from changed-file signals, falling back to documented default `readme → diagrams → improve`, and **MUST** keep `docs-improve` after the other two (FR-009, R7).
- **MUST** continue remaining sub-agents if one fails and surface the failure (FR-011).
- **MUST** emit one consolidated report (data-model §5) stating order, rationale, and per-sub-skill outcome (FR-010).

## Output schema

```
docs-all report
Order: readme → diagrams → improve   (reason: <signal | default fallback>)
- docs-readme    : success  — <1-line summary>
- docs-diagrams  : success  — <1-line summary>
- docs-improve   : failed   — <error>
```

## Acceptance mapping

US2 scenarios 1–4 → this contract. Tier 2 validation.
