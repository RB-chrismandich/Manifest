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
- **Cross-skill references are written qualified. Do not use `[[skill:...]]`.**
  Write the fully-qualified `bundle:other-name` directly in a SKILL.md body.
  A literal `/other-name` is caught by
  `configs/claude/scripts/skill_reference_check.py`, which is **blocking** for
  slash-form and dispatch-form references and advisory (ratcheted) for prose
  mentions.

  The `[[skill:...]]` token convention was **retired on 2026-08-27**. It was
  never rendered in production -- `skill_ref.py`'s only importer was a test, and
  packaging installs straight from `./plugins/<bundle>` -- so every token
  reached the model as literal text. All 106 across 45 files were rewritten to
  qualified commands, and `tests/python/test_skill_token_ratchet.py` now asserts
  that **no** `[[skill:` sequence reaches a packaged file. Guidance and gate
  landed together, deliberately: this doc previously taught the token form while
  nothing rendered it, so following the repo's own instructions produced literal
  text in shipped skills.

See [SKILL-NAMING.md](SKILL-NAMING.md) for the naming grammar itself.

## ADHD Guidance Generation

`manifest-i-have-adhd` owns `skills/i-have-adhd/SKILL.md` as its canonical
source. Run `python3 tools/sync_i_have_adhd.py` after editing it, then commit
the generated `guidance/always-on.md` and `devin/global-rule.md`. CI and
pre-commit run `python3 tools/sync_i_have_adhd.py --check` to reject drift.

The skill was adapted from `ayghri/i-have-adhd` at `2d19ad20`; its MIT license
remains in `plugins/manifest-i-have-adhd/LICENSE.upstream`.

## OMP compatibility declarations

The optional `omp` contract field records source compatibility, not installation,
activation, or qualification. Generated generic views mark OMP `qualified: false`;
the capability matrix keeps every OMP cell `UNVERIFIED` and gates release readiness
only on its six native harness cells. Preserve that boundary when regenerating
views or reviewing OMP metadata.

### Coordinator lifecycle adapter vs. qualification

The seventh coordinator `HarnessAdapter` supports `manifest install --harness omp`,
`reconcile`, `update`, and receipt-owned `uninstall` for the eight domain bundles
and ADHD addon. OMP 18.6.1's native `plugin list --json`, marketplace/install
registries, runtime lock, cache paths, and runtime links are cross-checked;
malformed, missing, disabled, stale, or conflicting state never converges.
Native `read skill://name` resolves skills inside their exact package, while
runtime, agent, executable, and MCP qualification remains explicitly unobserved.
`ServiceReport.native_inspection` separates package lifecycle from activation:
package READY never promotes OMP's optional/UNVERIFIED capability-matrix cell or
adds a seventh live-credential qualification harness.

Native commands use an explicit user scope and bound working directory/HOME.
Only the unambiguous default-user layout is supported. Named profiles, custom
config/agent roots, environment-file overrides, initialized XDG OMP roots, and
project inventories are refused before mutation. Merely setting an XDG variable
without initializing its `omp` root does not change the default layout. The
verified persistent local `release_root` is registered for published releases as
well as local checkouts; requested immutable Git provenance stays in the
coordinator release identity, not a fabricated native Git registration.

Full-receipt HMAC authority is bound to the trusted receipt parent. Ownership
records bind native root/scope, registration/source, version, runtime settings,
link identity, and cache content. Existing plugins are never adopted; an
identical unowned marketplace is reused without ownership. Actual creations
survive partial failures and are authenticated only after coherent receipt
merging. User modifications, foreign source references, conflicting target
caches, and changed same-version sources refuse destructive correction.

Native uninstall and targeted upgrade delete complete version caches. The
adapter exchanges each exact authenticated tree with a descriptor-held
placeholder, checks it again at the mutation boundary, and restores the real
tree on success or failure. Runtime package-name metadata remains in the
placeholder so native unlink targets the correct package. Restoration collisions
retain the recovery tree and report its location; unknown files are never
discarded. Unregistered caches remain preserved, so a conflicting same-version
reinstall is refused rather than force-overwritten.

Ordinary receipt-backed source/version reconciliation is supported. Native
source replacement uses guarded remove/add with prior-source recovery.
Durable cross-harness transactions are explicitly rejected during preparation:
OMP cannot safely compensate by re-registering retained caches without native
force overwrite. This is a visible pre-mutation refusal, not simulated rollback.

The eight domain contract versions move in lockstep. The ADHD portable addon is
independent and has its own versioned contract and marketplace entry.
`manifest-delegate` remains marketplace-only: it has no portable contract and is
not a coordinator requirement; issue #819 tracks any future change to that boundary.

## Live Parity Credentials

`.github/workflows/plugin-parity-live.yml` proves READY parity against real,
licensed, authenticated CLIs. It runs one job per harness, and each job may read
exactly **one** credential, resolved from its matrix row
(`secrets[matrix.secret]`). Configure these in the protected
`manifest-plugin-live` environment:

| Secret | Value | How the CLI reads it |
|--------|-------|----------------------|
| `LIVE_CLAUDE_CREDENTIAL` | Anthropic API key | `ANTHROPIC_API_KEY` |
| `LIVE_CODEX_CREDENTIAL` | OpenAI API key | `OPENAI_API_KEY` |
| `LIVE_GEMINI_CREDENTIAL` | AI Studio API key | `GEMINI_API_KEY` |
| `LIVE_CURSOR_CREDENTIAL` | Cursor dashboard API key | `CURSOR_API_KEY` |
| `LIVE_ANTIGRAVITY_CREDENTIAL` | AI Studio API key | `GEMINI_API_KEY` plus a pinned `modelProvider: gemini` |
| `LIVE_DEVIN_CREDENTIAL` | Full `credentials.toml` document | `~/.local/share/devin/credentials.toml`, mode 0600 |

Set one without exposing it to your shell history:

```bash
gh secret set LIVE_CLAUDE_CREDENTIAL --env manifest-plugin-live < key.txt
```

`tools/live_harness_setup.py` performs the install, credential placement, and
the CLI's own authentication probe. It is committed code on purpose: a step that
handles credentials must be reviewable, so no secret may carry executable shell.
The credential is withheld from the third-party installer's environment, the
probe failing fails the job, and a missing secret is an explicit `BLOCKED`
error rather than a silent skip.
