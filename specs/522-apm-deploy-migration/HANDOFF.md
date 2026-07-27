# Handoff — Feature 522, at the Phase 2/3 boundary

**Written**: 2026-07-27 · **Branch**: `522-apm-deploy-migration` · **State**: Phases 0–2 complete (30/59 tasks), nothing activated.

## Why the branch stops here

Phase 3 is the first phase that cannot be undone by `git revert`. It publishes a
package to a real git host, deletes 109 tracked files and four generators, and
switches the live deploy. Everything before it is additive and inert.

The branch is therefore mergeable as-is **and changes no behaviour for anyone**:

- `apm_domains.yml` is `domains: []` — nothing is gated, both legacy writers run
  exactly as before.
- `--enable-apm` defaults to **false** — no machine installs apm unless asked.
- The publish-free loop, the ownership report, the un-gate tool and the isolation
  harness are all new files nothing calls by default.

Verify that claim rather than take it: `apm_ownership_report.sh` prints
`skills … legacy` on a current checkout, and `bats tests/bats/` is 1356/1356.

## What Phase 3 will do, precisely

Read this before authorizing, because three of the four steps are one-way.

1. **T017** — write `apm_deploy_isolated.bats` and demonstrate each case FAILS
   against the current pipeline. Safe, but it lands red until T018 exists, so it
   cannot be merged alone without breaking CI on the branch.
2. **T018** — author the real `apm.yml` and **publish** Manifest as an APM
   package under a git host account. Irreversible: a published ref can be
   deleted but not un-fetched, and the publish gate records it permanently.
3. **Flip `apm_domains.yml` to include `skills`.** This is the step with live
   blast radius. From that commit until the APM deploy works, `~/.claude/skills`
   has **zero writers** — anyone who runs `./bootstrap.sh` from the branch gets
   no skills. It is intentional (Phase 2's checkpoint calls for it) and it is why
   T053's un-gate tool had to exist first, but it should not sit on a shared
   branch for long.
4. **T028/T030/T032** — delete four generators, remove 109 committed `.mdc`
   files, strip config deployment from `bootstrap/lib/deploy.sh`. One-way.

**Escape hatch, tested**: `apm_ungate_domain.sh skills --apply` returns the
domain to the legacy pipeline *and* reclaims what APM wrote (driven by the
lockfile's `deployed_files`, so other tools' skills in the same directory
survive). Then `./bootstrap.sh` repopulates. Proven by
`tests/bats/apm_ungate_domain.bats`.

## Things a reviewer should push back on

Listed because they are judgement calls I made, not facts.

1. **The drift fix is partial and the spec oversells it.** 170 script files stay
   on legacy rsync with no ownership manifest — scripts resolve siblings by
   relative path and some install to `PATH` outside the harness homes, which
   APM's target model has no notion of. Consequence: `deploy_reconcile.sh`
   **cannot** be retired, contrary to the spec's scope table. SC-001..SC-004
   should not be read as "drift is eliminated". See `migration-inventory.md`.
2. **`spec.md:36` was wrong and is now corrected.** It justified adopting apm
   partly on edit retention and `apm audit` drift detection. Neither exists.
   Adoption still stands on the lockfile ownership manifest, which is measured
   and real — but if that alone is not worth the migration, this is the moment
   to say so.
3. **FR-018's threats were re-aimed at a git host**, because "install by name"
   resolves `owner/repo`, not a registry. The mechanisms are unchanged; a
   residual risk is recorded that has no clean fix: on a git host the source
   repo and the distribution channel are the same asset, so repo compromise
   degrades the provenance gate more than the registry framing implied.
4. **Antigravity gets 0 files and that was accepted**, on the grounds that the
   primitives apm cannot serve there (instructions, hooks) are exactly the ones
   `deploy_antigravity_configs()` deliberately excludes, and skills arrive by
   symlink. If antigravity ever needs real hooks, this decision must reopen.

## Loose ends

- **Throwaway repo `RB-chrismandich/apm-spike-522` still exists** (private). Kept
  so cell (b) stays reproducible. Delete once Phase 1 no longer needs to re-run
  the measurement.
- **`.claude/CLAUDE.md` is at 3895/3900 bytes.** Five bytes of headroom. The next
  addition needs a real decision — delete something or raise the budget — not a
  squeeze. I did not raise it, because that gate exists to force the
  conversation.
- **`preserve_issue_sync_gates()` is now a migration shim** with a delete-me
  note. It can go once existing issue-hook opt-ins are assumed migrated (a
  re-run of `install_issue_hooks.sh --enable` moves one).
- **T017 is coupled to T018.** It is pure test code and otherwise safe, but it
  is red until the package exists, so the two land together or not at all.

## Verification commands

```bash
bats tests/bats/                                  # 1356/1356
uv run --project configs/claude pytest tests/python/ -q   # 737 passed
configs/claude/scripts/apm_ownership_report.sh    # skills … legacy, exit 0
pre-commit run --from-ref origin/main --to-ref HEAD
```
