# Contract: `branch-clean`

**Type**: Claude Code skill (`/branch-clean`) + helper `configs/claude/scripts/branch_clean.sh`.

## Invocation

```
/branch-clean [--apply] [--include-remote] [--stale-days N] [--protect <glob>...]
```

| Flag | Default | Meaning |
|------|---------|---------|
| (none) | dry-run | Preview candidates only; delete nothing (FR-018). |
| `--apply` | off | Perform deletions after confirmation. |
| `--include-remote` | off | Opt-in to remote-branch deletion; otherwise local-only (FR-016a). |
| `--stale-days` | config / 90 | Threshold for the `stale` category. |
| `--protect <glob>` | config defaults | Additional protected patterns. |

## Behavior contract

- **MUST** classify candidates by reason `merged` / `gone` / `stale` (FR-016, data-model §4).
- **MUST** default to local scope; remote deletion only under `--include-remote` (FR-016a).
- **MUST** never propose default/protected/current-HEAD branches (FR-017), and never enter the `merged` category for unmerged branches (FR-020).
- **MUST** default to dry-run; delete only with `--apply` + confirmation (FR-018).
- **MUST** report each deletion outcome incl. failures (FR-019).

## Output schema

```
branch-clean (dry-run | apply) — scope: local[+remote]
Merged into <default>:
  - feature/x        (merged)        [delete-candidate]
Gone upstream:
  - feature/y        (gone)          [delete-candidate]
Stale > Nd:
  - spike/z          (stale, 120d)   [delete-candidate]
Protected (skipped): main, release/*, <current>
Summary: K candidates; [dry-run: nothing deleted | applied: D deleted, F failed]
```

## Acceptance mapping

US4 scenarios 1–5 → this contract. Tier 1 on `--apply` (destructive), Tier 2 dry-run.
