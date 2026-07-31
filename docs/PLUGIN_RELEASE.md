# Plugin Bundle Versioning and Release

> Split out of [DEPLOY_OWNERSHIP.md](DEPLOY_OWNERSHIP.md) by spec 674 (T5.6):
> that page hit its 250-line cap, and the repo's own rule is to fan out to a
> sub-page rather than trim.
> Added by spec 674 (T5.6). Applies to the nine `plugins/<bundle>/` manifests
> and `.claude-plugin/marketplace.json`.

**`plugin.json` is the SOLE source of the version.** Measured, not assumed: it
wins at install time and the marketplace entry's copy is silently ignored — only
`claude plugin validate --strict` notices when the two disagree. A drift there
means users install `1.1.0` while the marketplace advertises `1.0.0`, with
nothing red anywhere. `tests/bats/bundle_partition.bats` asserts they match, so
the drift fails the build rather than shipping.

### What each bump means

| Bump | When | Why it is that level |
|------|------|----------------------|
| patch | a skill body or reference edit | no change to what loads or what it costs |
| minor | a skill added or removed, **or any description change** | both move the always-on token cost, which is user-visible |
| major | a skill moves between bundles, or a bundle is renamed | both break an installed set — use the marketplace `renames` map |

A description change being *minor* rather than patch is deliberate. Descriptions
are the always-on text: they are what the model sees every session whether or not
the skill fires, so editing one changes every user's context budget.

### The ritual

```bash
# 1. bump BOTH plugin.json and the marketplace entry to the same version
# 2. structural gates first — these need no CLI and always run
npx bats tests/bats/bundle_partition.bats
# 3. then the validator, if the CLI is present
claude plugin validate --strict .
claude plugin validate --strict plugins/<name>
# 4. commit, then tag
claude plugin tag --dry-run plugins/<name>
claude plugin tag plugins/<name> -m "<name> %s" --push
```

### Before touching apm or plugin state in a test

A test that shells out to a real deploy tool mutates the machine it is testing,
and the suite will not tell you. `apm_dev_sync` appends a local-path dependency
to `~/.apm/apm.yml` on every invocation; ten accumulated there during this
feature's own test development before anyone noticed, because nothing asserts on
that file. Diff `~/.apm/apm.yml` and `~/.claude/plugins/installed_plugins.json`
before and after any new suite that touches apm or plugins.
