---
name: deploy-drift-root-cause
description: Use when a deployed/live environment is missing expected state (symlinks, files, config) after a bootstrap/deploy — to decide whether it was an incomplete run or a deployer bug, fix the source of truth, and close the detector's blind spot.
---
# Root-Cause Deploy Drift, Don't Just Backfill

When a health check or manual inspection finds live state missing (e.g. only 1 of 5 expected symlinks exists), resist patching only the live symptom.

1. **Triangulate the sources of truth.** A deploy concern usually has three: the source definition (`configs/<x>/`), the human docs (`CLAUDE.md` / README manual-deploy section), and the deploy function that actually runs (`bootstrap/lib/*.sh`). Read all three and compare counts/contents.
2. **Classify the gap.** If source + docs agree on N but the deployer produces fewer, it is a **deployer bug** that recurs on every run — not a one-off incomplete run. State which it is, with evidence (cite file:line).
3. **Fix at the deployer, reusing existing helpers.** Prefer the shared helper siblings already use (e.g. `link_shared_assets`) over hand-rolling N individual calls — one definition keeps all consumers in sync if the set changes later.
4. **Backfill the live environment** so the user doesn't need a full re-bootstrap:
   ```bash
   for n in <missing items>; do ln -sfn "$SOURCE/$n" "$LIVE/$n"; done
   ```
5. **Strengthen the tests to assert the full contract, not the old subset.** Watch for helpers that skip-on-missing-target silently (`create_symlink` returning 0 with a warning) — these let stale tests pass while covering nothing. Seed all required targets in the test so the assertion is real.
6. **Close the detector's blind spot.** If a health-check/validation skill never inspected the drifted component, add it (scoped to enabled services only) so the same gap is caught next time.
7. **Verify before claiming done:** run the affected test suites, shellcheck the changed file, and confirm the live state resolves. Distinguish pre-existing lint infos from ones your edit introduced.
