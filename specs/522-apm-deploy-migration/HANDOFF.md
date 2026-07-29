# Handoff — Feature 522, at the Phase 2/3 boundary

**Written**: 2026-07-27 · **Branch**: `522-apm-deploy-migration` (merged, #636)
**State when written**: Phases 0–2 complete, nothing activated.
**State now**: superseded — see the status update below.

## ⚠️ Status update — 2026-07-28 (read this first)

This document describes the branch as it stood before merge. Three of its
claims no longer hold; the rest still does. Corrected rather than deleted,
because the reasoning below is why the sequence was safe.

- **"Nothing activated" is no longer true.** SC-006 landed in #654:
  `apm_domains.yml` now lists `skills`, apm owns `~/.claude/skills` (108 skills
  adopted), and `deploy_home_skills`/`sync-skills` stand down for the domain.
  Deploy preceded gating, deliberately — the reverse order leaves the domain
  writer-less on a live machine. Rollback is tested:
  `configs/claude/scripts/apm_ungate_domain.sh skills --apply`, then
  `./bootstrap.sh`.
- **Phase 3 ran — but only its first half.** `v0.0.1-apm-preview.1` is published
  (T018) and T017 is green. **The deletions did not happen and must not**:
  T028 (four generators) and T030 (109 committed `.mdc`) closed **VOID** because
  apm emits zero `.mdc` for a 108-skill package, so deleting them would destroy
  Cursor's rule integration with nothing taking over. `generate_cursor_rules.sh`,
  `generate_cursor_agents.py`, `generate_cursor_mcp.py`, `deploy_reconcile.sh`
  and all 109 `.mdc` files are **retained on purpose**. T032 closed
  not-applicable — though its stated reopen condition ("if and when SC-006 is
  decided and a domain is genuinely handed over") is now met and it deserves a
  second look. All 59 tasks closed: 42 delivered, 6 void, 1 not-applicable,
  3 measured-limited.
- **The ⛔ blocker below is resolved.** Constitution v3.0.0 amended Principle
  V.4 from preserve-and-report to **detect**-and-report, which is expressible
  with apm doing the write. The section is kept for the decision trail.

Still true and still worth reading: the reviewer push-backs (§"Things a
reviewer should push back on") — in particular that `deploy_reconcile.sh`
cannot be retired, since 170 script files remain on legacy rsync.

## Why the branch stopped here

Phase 3 is the first phase that cannot be undone by `git revert`. It publishes a
package to a real git host, deletes 109 tracked files and four generators, and
switches the live deploy. Everything before it is additive and inert.

The branch was therefore mergeable as-is **and changed no behaviour for anyone**
at the time of merge:

- `apm_domains.yml` was `domains: []` — nothing gated, both legacy writers ran
  exactly as before. (Now `domains: [skills]`, see the status update.)
- `--enable-apm` defaults to **false** — no machine installs apm unless asked.
- The publish-free loop, the ownership report, the un-gate tool and the isolation
  harness were all new files nothing called by default.

Verify rather than take it: `apm_ownership_report.sh` printed `skills … legacy`
on that checkout; it prints `skills … apm` today.

## What Phase 3 did, precisely

Written as a pre-authorization warning — three of the four steps are one-way.
Steps 1–3 have since run, step 3 in the reverse order described (deploy first,
gate second), which is why the writer-less window never opened on a live
machine. **Step 4 was refused**: T028/T030 closed VOID rather than delete a
capability apm cannot replace. The gating that caught it (T025/T026 as
preconditions) is the part worth copying.

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

## ✅ Resolved (was blocking): the constitution contradicted the shipped mechanism

**Resolved by constitution v3.0.0** — V.4 became detect-and-report, V.5 was
scoped. Kept for the decision trail; the analysis below is the reasoning that
forced the amendment.

Found by T035 after the rest of this handoff was written. **Phase 3 should not
start until this is decided**, because it is a decision, not an implementation.

Constitution v2.0.0 — authored by this feature, before the spike measured
anything — states as a MUST that a user-modified deployed file "MUST NOT be
silently overwritten; it MUST be preserved and reported" (Principle V.4). apm
silently overwrites, and cannot report. FR-034 was rewritten to match the
measurement, which moved the conflict out of the spec and into a contradiction
with the constitution rather than resolving it.

No Manifest-side guard fixes this. Re-hashing against `deployed_file_hashes`
buys *reported*; nothing buys *preserved*, because apm does the write. The
options are amend V.4, abandon apm for the homegrown fallback, or record a
scoped exception — see `constitution-consistency.md`. Principle V.3 (orphan
removal without a separate reconciliation pass) is also violated for the 170
scripts still on rsync.

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

- ~~**Throwaway repo `RB-chrismandich/apm-spike-522` still exists**~~ — deleted;
  the API no longer resolves it under a token that can see that owner's private
  repos. Cell (b) is no longer re-runnable from it; `decision-record.md` holds
  the measurement.
- **`.claude/CLAUDE.md` is at 3895/3900 bytes.** Five bytes of headroom. The next
  addition needs a real decision — delete something or raise the budget — not a
  squeeze. I did not raise it, because that gate exists to force the
  conversation.
- **`preserve_issue_sync_gates()` is now a migration shim** with a delete-me
  note. It can go once existing issue-hook opt-ins are assumed migrated (a
  re-run of `install_issue_hooks.sh --enable` moves one).
- ~~**T017 is coupled to T018.**~~ — both landed together, as required.
- **A retired skill is not pruned from an already-deployed home.** Retiring
  `print-tune-bambu` (#656) left `~/.claude/skills/print-tune-bambu/` and its
  `command_config.yml` `tool_policies` block in place on this machine. Whether
  apm reclaims a deleted skill on the next deploy, or a prune step is owed, is
  unmeasured — check before assuming the lockfile covers deletions.

## Verification commands

```bash
bats tests/bats/
uv run --project configs/claude pytest tests/python/ -q   # 737 passed
configs/claude/scripts/apm_ownership_report.sh    # skills … apm, exit 0
pre-commit run --from-ref origin/main --to-ref HEAD
```
