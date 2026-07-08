---
name: deploy-diagnose-drift
description: Use when a deployed/live environment is missing expected state (symlinks, files, config) after bootstrap/deploy — incl. entries that only miss already-bootstrapped machines — to classify the gap (incomplete run, deployer bug, preserve-on-existing drop) and fix the source of truth.
---
# Root-Cause Deploy Drift, Don't Just Backfill

When a health check or manual inspection finds live state missing (e.g. only 1 of 5 expected
symlinks exists), resist patching only the live symptom.

1. **Triangulate the sources of truth.** A deploy concern usually has three: the source definition
   (`configs/<x>/`), the human docs (`CLAUDE.md` / README manual-deploy section), and the deploy
   function that actually runs (`bootstrap/lib/*.sh`). Read all three and compare counts/contents.
2. **Classify the gap.** Read both the deployer's fresh-install and existing-install branches, then pick one class:
   - **Incomplete run** — the deployer is correct but didn't finish; a re-run fixes it.
   - **Deployer bug** — source + docs agree on N but the deployer produces fewer on every run. State
     it with evidence (cite file:line).
   - **Preserve-on-existing drop** — the deployer overwrites only *fresh* installs and **preserves**
     the file on already-bootstrapped machines (logs "existing found — preserving / manual merge may
     be needed" and skips). Then every repo-owned entry you later add to that file works on a clean
     machine and in tests but **silently never reaches existing installs**. Suspect this when the
     missing item is a recently-added entry in a config the deployer treats as user-owned
     (`settings.json`, `mcpServers`, files mixing auth tokens + repo defaults).
3. **Fix at the deployer, reusing existing helpers.** Prefer the shared helper siblings already use
   (e.g. `link_shared_assets`) over hand-rolling N individual calls — one definition keeps all
   consumers in sync if the set changes later. For a **preserve-on-existing** file that mixes repo-
   owned + user-owned content, don't switch it to wholesale overwrite (that clobbers user keys) —
   add a **structural merge** that inserts only the repo-owned entries and never mutates user keys.
   It must be idempotent (re-run adds nothing), fail-open on parse error (leave the file untouched
   and warn), and skip cleanly if the merge tool (`python3`/`jq`) is unavailable. Files the deployer
   already redeploys wholesale have no gap — don't add a merge path there.
4. **Backfill the live environment** so the user doesn't need a full re-bootstrap — for symlinks,
   relink the missing items; for a preserve-on-existing file, run the new merge into the live config
   now and confirm the entry resolves:

   ```bash
   for n in <missing items>; do ln -sfn "$SOURCE/$n" "$LIVE/$n"; done
   ```

5. **Strengthen the tests to assert the full contract, not the old subset.** Watch for helpers that
   skip-on-missing-target silently (`create_symlink` returning 0 with a warning) — these let stale
   tests pass while covering nothing. Seed all required targets in the test so the assertion is
   real. For a structural merge, seed a pre-existing target that already holds user keys and assert
   all four: (a) the repo entry is now present, (b) user keys are preserved, (c) a second run is
   idempotent (no duplicates), (d) malformed existing content leaves the file untouched.
6. **Close the detector's blind spot.** If a env-check/validation skill never inspected the
   drifted component, add it (scoped to enabled services only) so the same gap is caught next time.
7. **Verify before claiming done:** run the affected test suites, shellcheck the changed file, and
   confirm the live state resolves. Distinguish pre-existing lint infos from ones your edit
   introduced.
