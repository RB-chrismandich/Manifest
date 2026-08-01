# Deploy Ownership, Drift, and Rollback

> Who writes what into your home directories, how to detect when that goes
> wrong, and how to put it back.

**Last Updated**: 2026-07-29
**Audience**: contributors and anyone debugging a deployed environment
**Status**: mid-cutover — `skills` is APM-owned **and retired**; the harness
tree has moved; plugin bundles are not installed yet

---

## Current state, in one line

**`~/.claude/skills` is APM-owned (SC-006, 2026-07-28) and, since spec 674
Phase 2, also `retired:` — the three writers stand down and the four sibling
harness homes now resolve into `~/.manifest/skills`.** Every other domain is
still deployed by the legacy `bootstrap.sh` pipeline. `--enable-apm` still
defaults to false — the toggle governs whether bootstrap *installs* apm, not who
owns a registered domain.

### The three ownership states

`apm_domains.yml` was strictly two-state, and **unlisted meant the legacy writer
writes** — so handing a domain to plugins by deleting it from `domains:` would
re-arm two writers rather than stand any down. `retired:` is the third state:
nobody writes.

| Domain | Path | Writer today |
|---|---|---|
| `skills` | `~/.claude/skills` | nobody — apm-owned, `retired:`, tree frozen and still populated |
| `harness-skills` | `~/.manifest/skills` | `bootstrap.sh` (`deploy_home_skills … harness-skills`) |
| `plugins` | `~/.claude/plugins` | `claude plugin install` — **no bundle installed yet** |

`apm_ownership_report.sh` prints the rows that apply; the last two are
self-disabling, so their **absence is not a failure** pre-cutover.

**Not yet run anywhere**: Phase 4 (install the nine bundles, delete the
`~/.claude/skills` copies) and Phase 5 (retire the apm apparatus). Until then
`apm-dev-sync` is still how you refresh skills and `apm_drift_report.sh` is
still the per-file integrity check. Rollback for what *has* run is the Phase 0
tarball (`~/.manifest/pre-cutover-*.tgz`) — **not** `apm_ungate_domain.sh`,
since every apm-based rollback path is itself retired by this cutover and is
therefore circular.

Check it yourself rather than trusting that sentence:

```bash
configs/claude/scripts/apm_ownership_report.sh
# skills   ~/.claude/skills   apm
```

## The core idea: one writer per domain

A **domain** is a deployed area that must have exactly one writer. Two writers
under two ownership models is how deployed trees drift: each one overwrites what
it knows about and ignores what it doesn't, so files neither of them tracks
accumulate forever.

The registry `configs/claude/config/apm_domains.yml` names the domains APM owns.
Every legacy writer consults it and stands down for a listed domain.

| Domain | Path | Owner today |
|---|---|---|
| `skills` | `~/.claude/skills` (+ four harness symlinks) | apm |

Everything else — scripts, prompts, agents, config YAML — is legacy-owned and
**not part of the registry**. See
[migration-inventory.md](../specs/522-apm-deploy-migration/migration-inventory.md)
for why, including the scripts that are deliberately **not** migrating.

## Detecting drift

**Since spec 674 Phase 5, drift detection for the skill catalog is
[`plugin_drift_report.sh`](../configs/claude/scripts/plugin_drift_report.sh)**,
not `apm_drift_report.sh`. Constitution Principle V.3 makes detection a live
obligation for any path a mechanism claims, so retiring the tool without a
successor would have removed the control rather than migrated it.

What changed, stated plainly: apm recorded a sha256 per deployed file. Plugins
record only `gitCommitSha` + `version`, and `reconcile.yml` ignore-lists
`plugins`, so a hand-edit inside `~/.claude/plugins/cache/.../SKILL.md` is
invisible to `claude plugin` itself. The replacement compares the installed
bundle against its **directory-source** tree — the repo — which is exact for
this marketplace and honest about the rest: a git- or registry-sourced bundle
reports `UNCHECKED`, never clean, and "nothing checkable" exits 2 rather than 0.

One operational consequence worth knowing before you go looking for a bug:
`claude plugin update` is a **no-op when the version is unchanged**, so a body
edit does not reach users until `plugin.json` is bumped. That is what the patch
tier in [PLUGIN_RELEASE.md](PLUGIN_RELEASE.md) is for, and the drift report is
what tells you it was skipped.

```bash
configs/claude/scripts/apm_ownership_report.sh          # human-readable
configs/claude/scripts/apm_ownership_report.sh --json   # machine-readable
```

Exit 0 means every domain has exactly one owner. Exit 1 means one of two things,
and they are opposite problems:

- **`DOUBLE-CLAIMED`** — both pipelines write it. This is active drift. Either
  gate the legacy writer (add the domain to `apm_domains.yml`) or remove the APM
  package.
- **`UNOWNED`** — neither writes it. The area has silently stopped updating.
  Expected *only* during a migration hand-over window; a bug at any other time.

`/env-check` and `/config-audit` both surface this.

### Detecting user edits to deployed files

```bash
configs/claude/scripts/apm_drift_report.sh          # human-readable
configs/claude/scripts/apm_drift_report.sh --json   # machine-readable
```

Exit **0** clean, **1** drift found, **2** usage error *or* indeterminate. The
third matters if you wire this as a gate: a lockfile with no per-file hashes (a
local-path install produces one) cannot be checked, and exiting 0 there would
make "we never checked" and "we checked and it was fine" the same signal.

This is what Constitution V.4 requires and `apm audit` cannot provide — content
drift is not one of apm's four drift categories.

**What the ownership report does not detect**: content drift inside a deployed
file. `apm audit` does not either — it implements ref, orphan, config-MCP and
stale-file drift, and deployed-file *content* drift is not one of them. That gap
is covered separately, below.

## Deployed files are build outputs

**Do not hand-edit anything under `~/.claude/`, `~/.cursor/`, `~/.gemini/`,
`~/.codex/` or `~/.antigravity/`.** Those trees are reproducible from source and
any deploy may overwrite them without warning. Edit the source in `.apm/skills/`
or `configs/` and redeploy.

This applies to installers too. Manifest's own scripts write **source**, never a
deployed copy — the issue-hook opt-in, for example, lives in
`~/.manifest/issue_hooks.yml`, a file no package owns, precisely so a deploy
cannot destroy it.

## Deploying

```bash
./bootstrap.sh                       # everything
MANIFEST_DEPLOY_DOMAINS=config ./bootstrap.sh   # only the named domains
```

`MANIFEST_DEPLOY_DOMAINS` is a comma-separated allow-list. **Unset or empty
means all** — it is inert unless you ask for it. Its purpose is to let you
redeploy unmigrated domains without touching migrated ones, which is what makes
partial rollback possible.

### The skill development loop

```bash
apm-dev-sync            # publish-free: .apm/skills -> your HOME, via apm
sync-skills             # the legacy copy-based equivalent
```

Prefer `apm-dev-sync` when iterating: it tracks what it deployed, so a skill you
**delete** from `.apm/skills/` is also removed from your home. `sync-skills`
copies, and a copy cannot un-copy — deleted skills linger until someone notices.
`apm-dev-sync` needs `./bootstrap.sh --enable-apm`.

With more than one clone on the machine, say which one — it otherwise uses the
profile's `MANIFEST_ROOT` (last bootstrap's checkout) or the clone you are
standing in, which may be a real repo with no `.apm/skills`. The error names the
path it used.

```bash
MANIFEST_ROOT=/path/to/Manifest apm-dev-sync
```

### Who populates an APM-owned domain on a fresh machine

`./bootstrap.sh` runs the dev loop for an APM-owned skills domain **only when it
is empty** — otherwise a machine whose registry already gates `skills` gets none
at all, since bootstrap stands down and nothing takes over. A *populated* domain
is never touched: pushing a working tree over apm's published-tag deploy every
run is the double-claim the registry exists to prevent. An unpopulated domain is
a `verify_installation` **warning** naming `apm-dev-sync`, not a bootstrap error
— bootstrap is not the writer and must not take the blame.

## Activating a domain on a running machine

The migration plan gates a domain first, then deploys it. **On a live machine,
reverse that.** Gating first leaves the domain with no writer in between — on a
branch that is a documented window, on a running machine it means your skills
silently stop updating. A brief double-claim is the safer of the two failures.

```bash
apm install --global 'OWNER/REPO#TAG' --target claude   # 1. deploy
# 2. add the domain to configs/claude/config/apm_domains.yml
./bootstrap.sh                                          # 3. propagate the registry
configs/claude/scripts/apm_ownership_report.sh          # 4. expect: one owner, exit 0
```

**Check step 4 before trusting the handover.** apm will not adopt a directory
holding files it did not place, so a skill whose deployed copy carries local
build artifacts (`__pycache__`, `.pytest_cache` from running its tests) is
*skipped* — announced only as a single `[!] 1 file skipped` line that is easy to
miss. Gate the domain anyway and that skill is owned by neither pipeline. The
ownership report catches this and reports `PARTIAL`; clear the artifacts and
re-install.

## Rollback

To hand a domain back to the legacy pipeline mid-migration:

```bash
configs/claude/scripts/apm_ungate_domain.sh skills            # preview
configs/claude/scripts/apm_ungate_domain.sh skills --apply    # do it
./bootstrap.sh                                                # repopulate
```

Two steps happen, and the second is the one that is easy to forget: the domain
is removed from the registry (so the legacy writer resumes), **and** the files
APM deployed are reclaimed. Without the reclamation the domain ends up owned by
neither pipeline — the legacy writer only overwrites paths it knows about, so
anything APM added survives as an orphan.

Reclamation is driven by the lockfile's `deployed_files` inventory, not a glob,
so skills that other tools installed into the same directory are left alone.

## The pinned `apm` version

Pinning, hash verification, and the upgrade gate live in
[APM_PINNING.md](APM_PINNING.md). That whole apparatus is scheduled for
retirement by spec 674 Phase 5 (T5.4), which is why it is a separate page.

## Related

- [migration-inventory.md](../specs/522-apm-deploy-migration/migration-inventory.md) —
  every artifact classified, and what is *not* migrating
- [decision-record.md](../specs/522-apm-deploy-migration/decision-record.md) — the measured evidence behind these choices
- [HANDOFF.md](../specs/522-apm-deploy-migration/HANDOFF.md) — state at the Phase 2/3 boundary
- [APM_PINNING.md](APM_PINNING.md) — pinning and hash-verifying the `apm` binary (retiring with spec 674 Phase 5)
- [SKILL-NAMING.md](SKILL-NAMING.md) — the naming grammar and the add/rename/retire procedure

## Plugin bundles

Nine plugin bundles carry the skill catalog after spec 674's cutover.
Versioning rules, the release ritual, and the caution about tests that mutate
apm state live in [PLUGIN_RELEASE.md](PLUGIN_RELEASE.md).
