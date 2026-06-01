# Contract: `version-pin`

**Type**: Claude Code skill (`/version-pin`) + helper `configs/claude/scripts/version_pin.sh` + warn-only hook.

## Invocation

```
/version-pin [<path>] [--check] [--requested <pkg>=<version>] [--rule <id>]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `<path>` | working tree | File or directory to scan; unspecified ⇒ all recognized files in the tree. |
| `--check` | off | Warn-only: report violations + fixes, make NO edits (this is the hook mode). |
| `--requested pkg=ver` | latest stable | Pin the named dep to an exact requested version instead of latest stable. |
| `--rule <id>` | all matching | Limit to one rule-set entry. |

## Behavior contract

- **MUST** classify each parsed reference as `compliant` / `violation` / `bypassed` / `unresolved` (data-model §1).
- On-demand (no `--check`): **MUST** rewrite `violation` entries in place to specific version + hash where the rule's `hash` ≠ `none` (FR-003a).
- `--check` (hook): **MUST NOT** edit any file; **MUST** print each violation with its exact proposed pinned line; exit non-zero if any violation found (FR-005).
- **MUST** leave `compliant` and `bypassed` entries byte-for-byte unchanged (FR-004/FR-006); re-run is a no-op (SC-002).
- **MUST** treat missing native tool / offline / yanked / malformed file as `unresolved` warning — no partial rewrite (FR-007).

## Output schema (stdout, human + `--check` summary)

```
version-pin: <file>
  ✔ compliant   <name> <version> (<hash-prefix>)
  ✖ violation   <name> <current> → <resolved>==<version> --hash=sha256:<...>
  ⤼ bypassed    <name>            (reason: <text>)
  ⚠ unresolved  <name>            (<why>)
Summary: F files, V violations [fixed|reported], B bypassed, U unresolved
```

Exit codes: `0` = no violations (or all fixed on-demand); `1` = violations remain (`--check`); `2` = usage/config error.

## Acceptance mapping

US1 scenarios 1–6 → this contract. Tier 1 validation (security/supply-chain).
