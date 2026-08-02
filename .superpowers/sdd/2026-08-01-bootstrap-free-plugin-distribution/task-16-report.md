# Task 16 Report: Atomic Bootstrap Migration

## Changes

- Added the authoritative `legacy_inventory.yml` and deterministic generated
  `docs/PLUGIN_CAPABILITY_INVENTORY.md` renderer. It declares all twelve legacy
  output categories, ownership proof, disposition, recovery, and parity test.
- Added `MigrationService`, legacy scanning, proof-gated snapshots, private
  XDG recovery state, standalone stdlib `restore.py`, isolated HOME/XDG shadow
  install, process-lock detection, native verification, rollback, resume, and
  idempotent completed-receipt handling.
- Wired `ManifestService.migrate()` and `manifest migrate`, including an exact
  non-interactive `uvx --from manifest-agent` resume command on a blocked handoff.
- Added bootstrap-managed and mixed-user-state fixtures plus focused Python and
  Bats coverage for ownership, renderer constraints, one-writer ordering,
  rollback, unowned setting preservation, resumption, and idempotency.

## Validation

```text
uv run ruff check ...                         PASS
uv run python tools/render_capability_inventory.py --check  PASS
uv run pytest ...test_legacy_inventory.py ...test_migration.py ...test_service_*.py ...test_cli.py -q  44 passed
bats tests/bats/plugin_migration.bats         2 passed
git diff --check                              PASS
```

## Limitations

- Native harness CLIs were not invoked against a real home; tests use only
  temporary homes and fake adapters. A supported harness with an active known
  session lock or an ambiguous ownership proof is deliberately blocked and
  receives repair guidance.
- Mixed settings, credential stores, and all unlisted paths are retained; the
  native adapter remains responsible for its explicit owned-entry merge/removal.

## Review Repair

- Hardened ownership proofs: symbolic generated hashes and deploy-stamp text are
  never destructive evidence; only exact SHA-256 or exact symlink-target proof
  can retire an output. Legacy artifacts without such proof remain retained.
- Added missing Cursor, Gemini, Codex, Claude output, hook, agent, script, and
  managed-rule inventory records and corresponding completeness regression test.
- Migration shares `install.lock`, binds recovery state to release/checksum/
  optional capability/harness scope, journals quarantines before rename, and
  refuses unsafe recovery overwrites or legacy restoration after native cleanup
  failure. Resume now adds safely requested harness snapshots.
- Resume guidance preserves original `--source` or `--release`, repeated
  harness selectors, and all selected `--with` capabilities.

## Commits

- Initial implementation: `98707f9d2bd3b8a86d81438d0a829174ee24ab3c`
- Review repair: recorded by the subsequent Task 16 repair commit.
