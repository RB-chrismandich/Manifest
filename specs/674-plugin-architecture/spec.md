# Feature Specification: Claude Code Plugin Architecture

**Feature Branch**: `674-plugin-architecture`

**Created**: 2026-07-30

**Status**: Design — no files moved. Reopens the plugin half of feature 522 on refuted evidence.

**Input**: "Fan out and address each of our plugins in our Manifest repo. Rethink them from the ground up and ensure we take the appropriate action for commands, skills, agents, etc for all plugin features."

> ## ⛔ Partially superseded by [cutover-plan.md](cutover-plan.md) — 2026-07-30
>
> This document was written under a **phased, additive** assumption: publish plugins
> alongside a retained `~/.claude/skills`. The user then chose a **hard cutover**, where
> plugins become the SOLE source. Three conclusions below do not survive that change of
> requirement. The measurements are all still valid — the *decisions* built on them are not.
>
> | § | Says | Now |
> |---|---|---|
> | 2 · Mechanism A | `strict:false` + `skills[]` subset entries | **Reversed.** Subset entries land under version segment `unknown` — no `claude plugin tag`, no update semantics, no rollback pin — and the installer copies the whole source tree per entry, so 10 entries against one source = 10 full copies of all 108 skills on disk. Versioning is not optional when plugins are the sole source. Use Mechanism B (real dirs + real `plugin.json`). |
> | 18, 39, 103, 195, 352 · `manifest-core` | A core bundle holds the shared scripts | **Reversed.** `dependencies` is real and installs transitively (that part stands, and it does refute plugin-partition.md), but `${CLAUDE_PLUGIN_ROOT}` resolves ONLY to the loading plugin's own directory — there is no cross-plugin path form. Dependencies buy **installation, not resolution**: a script in core is unreachable from a dependent. Revisit only for a zero-skill core holding hooks/agents/MCP. |
> | 188 · What to ship | 2 entries now, split to ~6 later; never ship `manifest-runtime-ops` | **Reversed.** 9 Manifest bundles ship at once. `manifest-data-pipelines` and `manifest-ci` are dissolved; `manifest-runtime-ops` is **kept**, renamed `manifest-ops`, grown to 11. |
>
> **Not superseded and load-bearing**: everything under §251 *Verification*, §234 *the budget*,
> and §213 *two systems would own the same tree*. Read those as current.

## Why this exists

Feature 522 was opened with the question *"Would it make sense to migrate this
repo to a Claude plugin structure AND/OR Microsoft APM?"* It answered the APM
half and closed the plugin half as **measured-limited**, on this finding in
[`plugin-partition.md`](../522-apm-deploy-migration/plugin-partition.md):

> ⛔ **There is no dependency field.** … `manifest-core` cannot exist as a plugin
> others depend on, because the manifest format has nowhere to say so.
> **Disposition**: T038–T040 are closed as measured-limited. Reopen if apm gains
> plugin dependencies.

**That finding is false, and its reopen condition is the wrong condition.**

`apm pack` emits five keys. The document measured that output and generalised it
to the Claude Code plugin *format*. Probed directly against Claude Code's own
validator:

```
$ claude plugin validate --strict <plugin>
"dependencies": {"manifest-core": "^0.1.0"}    ✘ expected array, received object
"dependencies": ["manifest-core"]               ✔ Validation passed
"dependencies": [{"name":"x","version":"^0.1.0"}] ✔ Validation passed
```

`dependencies` is a supported `plugin.json` field — an array of `"name"`,
`"name@marketplace"`, or `{"name","version"}`. `claude plugin prune` exists to
"remove auto-installed **dependencies** that are no longer needed". Option 3 of
`plugin-partition.md` — a `manifest-core` plugin holding the shared scripts —
**is expressible today**. It never depended on apm.

Full evidence, including two of this document's own first-pass errors and their
corrections, is in [measured-facts.md](measured-facts.md).

## What is actually in the repo today

| | Count | Note |
|---|---:|---|
| Plugins in any commit | **0** | `git log --all --diff-filter=A -- 'plugins/*' '.claude-plugin/*'` is empty |
| Plugins staged, uncommitted | 1 | `adversarial-design-loop`, in sibling worktree `emdash/rich-tools-obey-8eua4` — not touched by this work |
| Skills | 108 | `.apm/skills/`, the single source of truth |
| Agents | 9 | `configs/claude/agents/` |
| Commands | **0** | and this is **correct** — see below |
| Hooks | 9 | user-scope entries in `~/.claude/settings.json`, unioned in by bootstrap |

## The four decisions

### 1. Commands — do nothing. Zero is the right number.

The user-facing framing of this task assumed commands were a gap. They are not.
From `plugin-dev`'s own `create-plugin` command, verbatim:

> **Note:** The `commands/` directory is a **legacy format**. For new plugins,
> user-invoked slash commands should be created as skills in
> `skills/<name>/SKILL.md`. Both are loaded identically — the only difference is
> file layout. `commands/` remains an acceptable legacy alternative.

Manifest already invokes every capability as `/skill-name` from
`skills/<name>/SKILL.md`. That is the *preferred* modern layout. Adding a
`commands/` tree would be a regression to a deprecated format.

**Action: none.** The ~60 user-invoked entry points identified per-domain in
[partition-map.md](partition-map.md) stay as skills. They are listed there only
to show which skills are verb-like, not as a conversion list.

### 2. Skills — partition by marketplace entry, not by moving files

Two mechanisms exist, and they are not equivalent.

**Mechanism A — marketplace subset entries.** A marketplace entry may carry
`strict: false` plus a `skills: []` array selecting a *subset* of skill
directories from a source path, with **no `plugin.json` in the source at all**.
Verified against the validator:

```json
{ "name": "manifest-docs",
  "source": {"source":"git-subdir","url":"https://github.com/…/Manifest.git",
             "path":".apm/skills","ref":"main"},
  "strict": false,
  "skills": ["./docs-all","./docs-improve","./docs-improve-readme","./docs-generate-diagrams"] }
```
→ `✔ Validation passed` (also under `--strict`).

Twelve official LSP plugins and three official skill bundles (`amd-skills`,
`box`, `learn-with-coursera`) ship exactly this way. AMD's repo contains more
skills than the four its entry lists — the subset selection is real.

**This requires moving zero files.** `.apm/skills/` stays the sole source of
truth, every existing gate keeps operating on the unchanged tree, and no script
is duplicated anywhere.

**Mechanism B — real plugin directories** with their own `plugin.json`, plus a
`manifest-core` plugin carrying the shared scripts that the others declare via
`dependencies`. Now known to be expressible (see above), but it requires
restructuring the tree and rewriting ~64 skills' path references.

**Decision: Mechanism A** — *under the phased assumption this section was written
for.*

> ⚠️ **Reversed by the hard-cutover decision.** The maintainer chose a hard
> cutover (2026-07-30). Under that requirement Mechanism A is disqualified, for
> two reasons discovered after this section was written:
>
> 1. A `strict:false` subset entry lands under the literal version segment
>    `unknown` — no `claude plugin tag`, no `claude plugin update` semantics, no
>    rollback pin, no way for a user to say which Manifest they run. When plugins
>    are the *sole* source of skills, versioning stops being optional.
> 2. The installer copies the **whole source tree per entry**, so ten entries
>    against one source path put ten full copies of all 108 skills on disk while
>    registering only the subsets.
>
> The cutover therefore uses **Mechanism B**: real plugin directories with real
> `plugin.json` manifests and real versions — but **without** a `manifest-core`
> or any `dependencies` key, because `${CLAUDE_PLUGIN_ROOT}` has no cross-plugin
> form. See [cutover-plan.md](cutover-plan.md).
>
> Mechanism A remains the correct choice for *additive* publishing, which is
> what this section assumed.

### 3. Agents — carry them, but only three plugins have a real claim

Of the nine agents in `configs/claude/agents/`, six are the pilotfish cost-tier
roster (`scout`, `Explore`, `mech-executor`, `executor`, `verifier`,
`security-executor`). These are **cross-cutting infrastructure**, not domain
components: they are the mechanism by which *any* skill delegates. Binding them
to one plugin means a user who installs only `manifest-docs` loses the tier
system entirely.

| Agent | Disposition |
|---|---|
| `scout`, `Explore`, `mech-executor`, `executor`, `verifier` | **Stay in `~/.claude/agents` via bootstrap.** Cross-cutting; not plugin components. |
| `security-executor` | Cross-cutting, but has a defensible claim to a security bundle. Keep in bootstrap. |
| `dependency-guardian` | Domain-specific (supply chain) → runtime-ops bundle if that ever ships. |
| `context-chronicler`, `compatibility-translator` | Manifest-internal (session compaction, cross-platform sync) → workspace bundle. |

**Action: none this pass.** Mechanism A entries carry skills only; agents keep
deploying via bootstrap. This is not a limitation — it is correct, because the
tier roster must be present regardless of which domains a user installs.

### 4. Hooks and MCP — do not move them

Manifest's nine hooks are **user-scope** entries in `~/.claude/settings.json`.
Three of them (`subagent_model_default.py`, `block_cwd_delete.py`,
`guidance_hint.py`) are deliberately domain-free machine-wide policy.

- Attaching them to one plugin means a user installing a different plugin gets
  no deletion guard and no model-pin enforcement.
- Attaching them to every plugin means N registrations of the same script.
- Plugin hooks (`hooks/hooks.json`) are a **different mechanism** from the
  settings.json hooks Manifest ships. Moving them is a rewrite, not a repackage.

MCP servers are already correctly handled: only Context7 ships registered, the
rest are opt-in via `./bootstrap.sh --install-mcp` (#646).

**Action: none.** Both stay with bootstrap.

## The partition

Three independent classifiers (subject / user-journey / runtime-coupling) each
assigned all 108 skills; a fourth reconciled them.
**69/108 (64%) placed identically by all three lenses.** Full map, per-skill
tables, 39 dispute resolutions and 14 structural problems:
[partition-map.md](partition-map.md).

| Bundle | Skills | Cross-lens support | Ship? |
|---|---:|---|---|
| `stitch-design` | 18 | **18/18 unanimous** — strongest in corpus | **Yes — separate** |
| `manifest-forge` | 18 | merged by default, not agreement | Later |
| `manifest-code-quality` | 19 | 8/19 unanimous | Later |
| `manifest-workspace` | 17 | 9/17 unanimous | Later |
| `manifest-security` | 8 | 6/8 unanimous | Later |
| `manifest-spec-planning` | 7 | 6/7 unanimous | Later |
| `manifest-runtime-ops` | 6 | **0/6 unanimous** | No |
| `manifest-data-pipelines` | 6 | **one lens only** | No |
| `manifest-ci` | 5 | **0/5 unanimous** | No |
| `manifest-docs` | 4 | **4/4 unanimous** | Later |

## What to ship

> ⛔ **SUPERSEDED in full** by [cutover-plan.md](cutover-plan.md) Phase 3–4. Retained as the
> record of what the *additive* plan would have been. Under the hard cutover: 9 Manifest bundles
> ship together — `manifest-forge` (18), `stitch-design` (18), `manifest-code-quality` (22),
> `manifest-workspace` (17), `manifest-ops` (11), `manifest-security` (10),
> `manifest-spec-planning` (7), `manifest-docs` (4), `manifest-graphify` (1) — plus the sibling
> branch's `adversarial-design-loop`. No `manifest-core`, no `strict:false` entries, and the
> "never ship `manifest-runtime-ops`" line below is reversed: it is kept and grown to 11.

**Phase 1 — two entries, zero file moves.**

1. **`stitch-design`** (18 skills). Unanimous across all three lenses, zero
   `~/.claude/` coupling, self-contained. Vendored from an external source, so
   the `manifest-` prefix would imply provenance this repo does not have.
2. **`manifest-core`** (90 skills). Everything else, as one bundle, via a single
   `strict:false` entry.

This is deliberately *not* the ten-way split. Ten entries would each advertise a
domain while the skills inside them still resolve `~/.claude/scripts/…` — a user
installing one bundle gets skills that silently need the other bundles' scripts.
One core bundle makes that prerequisite honest.

**Phase 2 — split `manifest-core` domain by domain**, in descending cross-lens
support: `manifest-docs` (4/4), `manifest-spec-planning` (6/7),
`manifest-security` (6/8), `manifest-forge`, `manifest-code-quality`,
`manifest-workspace`. Each split is a marketplace-entry edit, reversible, and
gated on the verification below.

**Never ship** `manifest-data-pipelines` (one lens only),
`manifest-runtime-ops` (0/6 unanimous), or `manifest-ci` (0/5 unanimous, and one
63-line detector away from being part of forge).

## The blocking problem: two systems would own the same tree

This is the one issue that has no clean answer and must be decided before Phase 1.

`apm` has owned `~/.claude/skills` since SC-006 (2026-07-28) and deploys all 108
skills from a published tag. A marketplace entry would install the *same* skills
into `~/.claude/plugins/cache/`. A user with both gets **every skill registered
twice**.

They are mutually exclusive for the same skill. The options:

| Option | Consequence |
|---|---|
| Marketplace replaces apm for skills | Fixes the budget problem. Requires `apm_ungate_domain.sh skills --apply`. Loses apm's lockfile hash-tracking. |
| apm keeps everything; marketplace ships only `stitch-design` | Smallest change. Budget problem persists for the other 90. |
| Both, with apm's `reconcile.yml` ignore-listing plugin-sourced skills | Most complex; two sources of truth, which is what 522 existed to remove. |

**Recommendation: option 2 for Phase 1**, because `stitch-design` is the one
bundle whose skills are vendored and self-contained, so removing them from the
apm tree costs nothing. Decide option 1 vs 3 before Phase 2.

## Why this matters: the budget

| Source | Skills | Always-on tokens |
|---|---:|---:|
| Manifest `.apm/skills` | 108 | ~6,700 |
| Installed plugins | 58 | 3,469 (measured) |
| **Total** | **166** | **~10,170** |

`skillListingBudgetFraction` is 0.05 → ~10,000 tokens. The session is **at the
cap**, with Manifest consuming 67% of it. On the *default* fraction of 0.01
(2,000 tokens), Manifest alone is **3.35× over**, and skills are rivalrous —
budget exhaustion drops descriptions, and a name-only skill never fires.

`tests/bats/context_budget.bats` caps `.apm/skills` at 29,000 chars and reports
healthy headroom (26,860). It is blind to installed-plugin skills competing in
the same budget.

## Verification — all three settled 2026-07-30

Performed against a throwaway `zzprobe` local marketplace, then fully removed
(environment returned to baseline: 28 plugins, 2 marketplaces).

**V1 — Does `dependencies` resolve at install time? YES.**

```
$ claude plugin install zz-leaf@zzprobe --scope user
✔ Successfully installed plugin: zz-leaf@zzprobe (scope: user) (+ 1 dependency: zz-core)
```

`zz-leaf` declared `"dependencies":["zz-core"]`. The dependency auto-installed.
This is the install-time confirmation the validator alone could not give.

**V3 — Does a subset entry select correctly? YES, with one nuance.**

Source tree contained `zz-a`, `zz-b`, `zz-c`; the entry listed only `zz-a` and
`zz-b`. `claude plugin details zz-subset` reported `Skills (2)  zz-a, zz-b`.

The nuance: **the installer copies the whole source tree to disk** — `zz-c` was
present under the cache — but only the listed subset *registers* and costs
listing budget. Disk is not the constraint; the listing is.

On-disk layout: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/…`.
A versioned plugin gets its real version and skills live under
`<version>/skills/<name>/SKILL.md`. **A `strict:false` subset entry gets the
literal version segment `unknown`** and the selected skill dirs sit at the root
of that segment. Uninstall leaves a `.orphaned_at` marker rather than deleting.

**V2 — Can per-skill policy travel? PARTLY, and there is a clean mechanism.**

Surveyed frontmatter keys across all 260 installed `SKILL.md` files:

| Key | Skills using it | Verdict for Manifest |
|---|---:|---|
| `allowed-tools` | **30** | Works. `tool_policies` allowed/forbidden lists can migrate to frontmatter. |
| `argument-hint` | 9 | Works. |
| `model` | **0** | No shipped skill uses it. **Do not assume model pins work in SKILL.md.** |
| `metadata` / `retrieval` / `chainTo` / `validate` | 57 / 55 / 49 / 26 | Arbitrary custom keys are tolerated. |

The last row is the answer. Vercel ships structured `metadata:` (priority,
`pathPatterns`, `importPatterns`, `bashPatterns`) and `validate:` rule arrays in
SKILL.md frontmatter, consumed by its own tooling. Manifest can do the same:
put `metadata: {validation_tier, subagent_model, parallel_agents}` in each
SKILL.md and have Manifest's existing hooks read it. **Policy then travels with
the skill into any bundle**, which resolves the partition's most expensive
structural problem.

Cost: none against the listing budget — only `name` and `description` are
listed. (part-forge ships 8 skills with rich frontmatter at 28 tok/skill.)

Caveat that stands: `claude plugin validate --strict` does **not** validate
SKILL.md frontmatter — it accepted a bogus `validation_tier: 1`. Any frontmatter
policy scheme needs Manifest's own gate, not the plugin validator.

**Two further findings from the probes:**

- **`${CLAUDE_PLUGIN_ROOT}` resolves to the loading plugin's own directory.**
  There is no cross-plugin path form. So `dependencies` buys *installation*, not
  *path resolution* — a skill in one bundle cannot portably address a script in
  another. **Shared scripts therefore cannot live in a dependency plugin.** They
  stay with bootstrap at `~/.claude/scripts/`.
- **`userConfig` is a real `plugin.json` field** — a record keyed by option name,
  each requiring `title`, `type` (`string|number|boolean|directory|file`) and
  `description`; it rejects `enum`, `options`, `secret`, `required`. It is
  install-time *user* configuration and **cannot carry per-skill policy**.

## Fixes to land regardless

These are independent of whether any bundle ships.

1. **Correct `plugin-partition.md`.** Its ⛔ section is wrong on the central
   fact, and its "22 of 108 skills (20%) depend on a shared script… the other
   80% are self-contained" is wrong twice: 43/108 depend on a named script, and
   only **44/108 (41%)** are self-contained once `~/.claude/` config and state
   references are counted.
2. **Adopt `claude plugin validate --strict` as a CI gate** the moment any
   `.claude-plugin/` file is committed. It catches unrecognized fields, missing
   metadata, and non-existent component paths.
3. **Fix the existing `adversarial-design-loop` plugin** (sibling worktree, not
   edited here): `skills/render-verify/SKILL.md` instructs
   `python3 tools/render_and_scan.py` and refers to `scripts/` by bare relative
   path. Both forms are explicitly forbidden — it must use
   `${CLAUDE_PLUGIN_ROOT}`. Its marketplace entry also uses `keywords` (1 of 276
   official entries do) instead of `category` (262 of 276) and omits `homepage`
   (260 of 276).
4. **Do not add `"$schema"`** to any marketplace.json. The URL the official
   marketplace declares — `https://anthropic.com/claude-code/marketplace.schema.json`
   — returns **HTTP 404**.
5. **Note for `plugin.json` authors**: `strict` and `category` belong in the
   *marketplace entry*, not `plugin.json`; the validator warns on both. `skills`
   *is* a valid `plugin.json` path field, contradicting the `plugin-structure`
   skill's claim that "There is no `skills` path field documented".

## Disposition

No files moved. No plugin shipped. The ten-way partition is retained as a **map**
— useful for organising `.apm/skills`, driving `command_categories.yml`, and
telling `/help` which neighbourhood a skill lives in — not as a shipping plan.

The one thing that changed materially: `manifest-core` is no longer impossible.
Feature 522's plugin half should be reopened on that basis, not left waiting on
an apm capability that was never the blocker.

> ⛔ **Superseded 2026-07-30.** "`manifest-core` is no longer impossible" was correct about
> `dependencies` (verified: transitive install works, which does refute plugin-partition.md) but
> wrong about what that buys. `${CLAUDE_PLUGIN_ROOT}` resolves only to the loading plugin's own
> directory, so a shared script inside a core bundle is unreachable from a dependent —
> **installation, not resolution**. `manifest-core` remains impossible *as a shared-script host*,
> which was its only purpose here. Also superseded: "no files moved / the ten-way partition is a
> map, not a shipping plan". Under the hard cutover the files DO move
> ([cutover-plan.md](cutover-plan.md) Phase 3) and the partition ships as **9** bundles.
