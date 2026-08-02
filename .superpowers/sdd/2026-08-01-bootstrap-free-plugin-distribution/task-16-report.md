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

## Second Review Repair

- Completed receipts now reject a differing release, source commit, archive
  checksum, or optional capability set before returning READY. Compatible
  sequential harness migrations extend recovery state rather than treating the
  original harness list as immutable.
- Native cleanup must return READY before legacy output is restored, including
  interrupted installs. Each rename rechecks its proof and snapshot digest;
  pending quarantine locations are usable by rollback and standalone recovery.
- Standalone recovery uses the same tree digest as snapshots and never deletes
  a changed destination. Added remaining deployed Python project/lock and
  retired APM helper inventory records; unproven retained writers block with
  explicit manual-parity guidance.

## Final Scoped Repair

- Retained mixed and coordinator-owned legacy writers now block migration just
  like bundle-owned and retired writers. Only explicitly user-owned or native
  credential state is excluded. The regression creates the legacy `manifest`
  coordinator and proves migration is BLOCKED without writing a receipt.

## Mixed Settings Repair

- User-only mixed JSON files are now preserved and no longer block migration.
  Invalid or Manifest-shaped mixed entries fail closed with a path-specific
  instruction to remove only the legacy entry; neither the file nor unrelated
  user settings are rewritten. Regression coverage verifies both outcomes.

## Commits

- Initial implementation: `98707f9d2bd3b8a86d81438d0a829174ee24ab3c`
- Review repair: recorded by the subsequent Task 16 repair commit.
