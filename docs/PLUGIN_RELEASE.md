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

## Qualified names

Once a skill ships inside a bundle it is reachable **only** as
`<bundle>:<name>` — `/manifest-docs:docs-all`, not `/docs-all`. There is no bare
alias and no fallback: a bare `/name` is an Unknown command. This is the single
largest accepted cost of the cutover (spec 674) and it applies to all 108
skills, including the ones skills invoke from inside their own bodies.

Two consequences when adding, renaming, or moving a skill:

- **The bundle is part of the name.** Moving a skill between bundles is a
  user-visible rename, which is why the table above treats it as a major bump.
- **Cross-skill references must be resolved, not hardcoded.** Write
  `[[skill:other-name]]` in a SKILL.md body and let
  `configs/claude/scripts/skill_ref.py` render it. A literal `/other-name` is
  caught by `configs/claude/scripts/skill_reference_check.py`, which is
  **blocking** for slash-form and dispatch-form references and advisory
  (ratcheted) for prose mentions.

See [SKILL-NAMING.md](SKILL-NAMING.md) for the naming grammar itself.

## Mirrored Plugin Provenance

`manifest-i-have-adhd` is refreshed only with `tools/sync_i_have_adhd.py` from
an already checked-out, reviewed Git commit. The tool reads regular-file bytes
directly from the pinned commit object, rejects symlinks/submodules, verifies
checksums in `upstream-lock.json`, and never fetches mutable upstream content.
