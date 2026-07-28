# Deploy Ownership, Drift, and Rollback

> Who writes what into your home directories, how to detect when that goes
> wrong, and how to put it back.

**Last Updated**: 2026-07-27
**Audience**: contributors and anyone debugging a deployed environment
**Status**: the APM pipeline is **built but not activated** — see *Current state*

---

## Current state, in one line

**Everything is deployed by the legacy `bootstrap.sh` pipeline today.** The APM
pipeline exists, is tested, and is switched off (`apm_domains.yml` is empty,
`--enable-apm` defaults to false). Nothing in this document changes your setup
until a domain is registered.

Check it yourself rather than trusting that sentence:

```bash
configs/claude/scripts/apm_ownership_report.sh
# skills   ~/.claude/skills   legacy
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
| `skills` | `~/.claude/skills` (+ four harness symlinks) | legacy |

Everything else — scripts, prompts, agents, config YAML — is legacy-owned and
**not part of the registry**. See
[migration-inventory.md](../specs/522-apm-deploy-migration/migration-inventory.md)
for why, including the scripts that are deliberately **not** migrating.

## Detecting drift

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

`apm` is pinned by version **and** sha256 in `bootstrap/lib/install.sh`, and
installed fail-closed: a checksum mismatch, a failed download, or a missing
checksum tool leaves apm uninstalled rather than falling back to an unverified
binary.

The digest is not a corruption check — it is the **provenance**. PyPI ties
`apm-cli` to no repository (no `home_page`, no `project_urls`, no author), so
the digest recorded at verification time is the only thing asserting the
artifact's identity.

### Upgrading

Bumping the version without re-recording the digest silently disables the only
check there is, so the pin is gated:

1. Re-run the deployment matrix against the new version in an isolated HOME.
2. Confirm idempotence — install twice, assert byte-identical.
3. Confirm equivalence — the new version's output matches the old one's for an
   unchanged source tree.
4. Update **both** `bootstrap/lib/install.sh` and
   `configs/claude/config/apm_pin_verified.txt`.

`tests/bats/apm_upgrade_gate.bats` fails if the two disagree. That forces a bump
to arrive with an explicit "I re-verified this" — it cannot prove you ran steps
1–3, and its own record file says so.

### Offline / air-gapped install

```bash
APM_WHEEL_LOCAL=/path/to/apm_cli-0.26.0-py3-none-any.whl ./bootstrap.sh --enable-apm
```

Skips resolution and download entirely — no network, no registry. **The checksum
is still verified**: bringing your own file is not evidence about what is in it,
and an air-gapped install is exactly when nobody is watching. A missing local
artifact is an error, never a silent fallback to the network.

## Related

- [migration-inventory.md](../specs/522-apm-deploy-migration/migration-inventory.md) —
  every artifact classified, and what is *not* migrating
- [decision-record.md](../specs/522-apm-deploy-migration/decision-record.md) — the measured evidence behind these choices
- [HANDOFF.md](../specs/522-apm-deploy-migration/HANDOFF.md) — state at the Phase 2/3 boundary
