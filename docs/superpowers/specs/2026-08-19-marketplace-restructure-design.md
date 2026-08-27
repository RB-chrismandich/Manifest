# Marketplace Restructure — Design

**Status**: Proposed (adversarially reviewed 2026-08-19)
**Date**: 2026-08-19
**Baseline**: commit `ad1faee3` — 10 bundles, 122 skills. Every count below is
re-derived at this commit; earlier drafts mixed pre- and post-consolidation
snapshots.
**Scope**: `plugins/`, `tools/generate_plugin_views.py`,
`src/manifest_agent/plugin_view_renderers.py`,
`schemas/manifest-capabilities.schema.json`, `.claude-plugin/marketplace.json`, CI
**Related**: [docs/SPEC-SYSTEMS.md](../../SPEC-SYSTEMS.md), [specs/674-plugin-architecture](../../../specs/674-plugin-architecture/)

---

## 1. Problem

An end-to-end audit (12 agents), an empirical probe pass (11 agents), an external
review, and five adversarial refutation rounds established four problems.

### 1.1 Bundles are incorrect under a plugin-only install

Bundles install independently, but skills reference files living in *other*
bundles or only in the bootstrap-deployed home tree.

| Defect | Count | Evidence |
|---|---|---|
| Cite a "bundled" `sub-agent-dispatch.md` | **21 skills / 5 bundles** | exists only in `manifest-spec-planning/runtime/references/` |
| Cite bare `command_config.yml` | 12 occurrences / 11 skills / 3 bundles | exists only at `configs/claude/config/` post-bootstrap |
| Cite `harness-routing.md` | 1 skill | `manifest-delegate`, monorepo path |
| Duplicated-and-diverged references | 2 files | `antipatterns.md`, `code-constitution.md` |

`sub-agent-dispatch.md` is what pins sub-agents to Sonnet, so the model-tier
policy silently does not apply outside `manifest-spec-planning`.

### 1.2 Hook files do not load

3 of 6 hook files fail, differently per harness.

| File | Defect | Claude Code | Codex |
|---|---|---|---|
| `manifest-workspace/hooks/manifest-hooks.json` | `hooks` is a flat list with invented events | dead | dead |
| `manifest-ops/hooks/version-pin.json` | custom `_manifest` key | loads (warns) | file rejected at parse |
| `manifest-ops/hooks/compose-commandments.json` | custom `_manifest` key | loads (warns) | file rejected at parse |

**Caveat on the two `manifest-ops` rows.** Codex does reject the file at parse
time on `_manifest`, but that is not the only blocker:
`plugins/manifest-ops/manifest-capabilities.yml` and
`docs/PLUGIN_CAPABILITY_MATRIX.md` already mark both hooks DEGRADED for Codex
because Codex has *no native file-save hook surface*. Stripping `_manifest` is a
portability fix (Constraint 2); it does **not** restore Codex functional parity.
The trigger-surface gap is a Codex-side limitation outside this spec.

### 1.3 Skills invoke other bundles' skills, with no dependency declared

The same defect class as §1.1, one level up: not a missing *file*, a missing
*skill*. Of 105 `[[skill:…]]` tokens in plugin Markdown, **93 name a skill that
does not exist in the citing bundle**, and **no plugin manifest declares
`dependencies`** (verified across all 10).

`manifest-code-quality/skills/python-refactor/SKILL.md:14-15` calls
`parallel-agent` mandatory; that skill lives only in `manifest-workspace`. A user
installing just `manifest-code-quality` gets an instruction to invoke something
that is not installed — so a "mandatory" verification step silently does not run.

This is why token rendering (§4 Phase 0 item 4) is necessary but **not
sufficient**: turning `[[skill:parallel-agent]]` into
`/manifest-workspace:parallel-agent` produces a correctly-spelled command that is
still unavailable. Constraint 1 cannot be satisfied without a dependency-closure
decision.

### 1.4 The always-on listing is over budget

Claude Code caps the always-on listing at `skillListingBudgetFraction`
(default 0.01 = 1% of context) and, on overflow, drops descriptions starting with
the least-invoked skills — silently making them untriggerable.

- ~14,978 always-on tokens across 36 installed plugins; Manifest's 10 bundles ≈ 6,211–6,760.
- Official marketplace: median 1 skill / 73 tok per plugin. Manifest: median 8.5 skills / 543 tok.
- Four Manifest bundles exceed the highest skill count anywhere in the official catalog (14).

**Evidence caveat.** The live truncation warning observed during this work
(*"Skill descriptions were shortened to fit the skills context budget"*) came from
**Codex**, a different harness with a smaller window — not Claude Code. The
same-day Claude Code probe showed no truncation at 207–209 skills. The problem is
therefore a trend on a growing catalog crossing a fixed-fraction budget, not a
demonstrated Claude Code failure today. §6's caveat on token figures also applies.

---

## 2. Constraints

1. **Primary consumer is external users installing individual bundles.** Bundles
   must be correct under a plugin-only install; bootstrap is secondary.
2. **Open Agent Skills spec portability is tier-1.** Only `name`, `description`,
   `license`, `compatibility`, `metadata`, `allowed-tools` are portable. Currently
   violated in 7 places (`version:` ×6 in stitch-design, `disable-model-invocation:`
   ×1 in i-have-adhd).
3. **Phase 1 and 2a preserve every public qualified command** — 2a-ii only via a
   tested shim; anything that cannot keep its command moves to 2b. All three
   stages are *versioned* (see §9a); "preserves commands" is the compatibility
   promise, not "requires no version bump". **Phase 2b is the one explicitly
   breaking stage.**

An earlier "zero capability loss, nothing renamed" constraint was set in
conversation before we established that the additive path is structurally rejected
(§5.1). Superseded by constraint 3.

## 3. Non-goals

- Model-tier pinning on `context: fork` dispatches (§5.4) — its own spec.
- Broad adoption of `context: fork` / `agent:`. They fix reference correctness and
  save invoke-time context, but buy **zero** always-on listing budget (§6).
- Raising `skillListingBudgetFraction` as a shipped remedy.

---

## 4. Decision

Four stages. Phase 0 is blocking design work. Phase 1 and 2a preserve every public
qualified command and ship independently; both are still versioned (§9a). Only 2b
is a breaking migration.

### Phase 0 — Design the blocking mechanisms (BLOCKING)

**Phase 1 cannot start until this lands.** Five successive adversarial rounds
established that the generator lacks the machinery Phase 1 assumes, and that two
further problems — §1.3 dependency closure and the true token corpus — must be
settled before any repair or vendoring begins.

- `schemas/manifest-capabilities.schema.json` `$defs.skills` is `{root, include}`
  with `additionalProperties: false` and **no `compatibility` field** — unlike
  `$defs.component`, which has one. Skills are the one component category with no
  per-harness axis.
- `_discover_skills()` computes a single skills-path tuple fed unchanged into both
  `_claude_view()` (`./skills/{name}`) and `_generic_harness_surface()`
  (`skills/{name}`). No code resolves a different skill root per harness.
- `$defs.component` has `{id, path, compatibility}` only — no `source` or `sha256`
  field, and `additionalProperties: false` blocks ad hoc extension. No function
  reads content from outside a bundle's own directory.
- Skill discovery globs `*/skills/*/SKILL.md`, so a portable variant cannot be a
  second file in the same directory.

Phase 0 must decide and design:

1. A canonical-source + digest field for vendored references, and the cross-bundle
   read logic to populate it.

   **The canonical source is not a greenfield choice — three candidates already
   exist and have already diverged.** `configs/claude/references/{antipatterns,
   code-constitution,sub-agent-dispatch}.md` all live outside `plugins/` today and
   are already consumed by the deployed orchestration guide's Reference Index.
   Phase 0 must pick among them explicitly, and reckon with two problems:
   - **The obvious candidate is itself non-portable.**
     `configs/claude/references/antipatterns.md` cites
     `native-harness/config/knowledge_base.yml` and `docs/KNOWLEDGE_BASE.md` as its
     live source of truth — bootstrap-only paths, i.e. **the exact §1.1 defect
     class this phase exists to eliminate**. Adopting it unchanged would vendor the
     defect into every citing bundle. Either it is rewritten to be portable-safe
     (coupling home-deploy edits to plugin correctness) or a new file is authored
     and `configs/claude/references/` becomes an unmanaged fourth copy. Decide which.
   - **A byte-identical-copy model would erase deliberate per-bundle divergence.**
     `manifest-code-quality/skills/code-audit/references/antipatterns.md` is a
     verbatim copy of the non-portable text, while
     `manifest-security/runtime/references/antipatterns.md` was **deliberately
     rewritten** — different purpose statement, `[[skill:learning-capture]] query`
     in place of the bootstrap citation, explicitly framed as working "without
     requiring another plugin or a shared home config". A mechanical copy destroys
     that. The mechanism needs either a per-bundle framing seam or an explicit
     decision that the security variant wins everywhere.

   **Also settle the "which generator" ambiguity.** §4 1.1's prose says "the
   generator copies… and `--check` hash-verifies", but everywhere else in this
   document "the generator" means `generate_plugin_views.py`, while round-1 Q1
   assigned vendoring to a *separate* `tools/vendor_shared_references.py`. These
   imply different architectures: either vendored files land upstream as ordinary
   declared components that `generate_plugin_views.py` merely validates (keeping
   Phase 0's three mechanisms separable), or they become entries in
   `_bundle_expected_views()`'s `expected` dict, making `generate_plugin_views.py
   --check` the real drift gate and entangling exactly what R4 warns about. R4
   defers this to post-hoc measurement; it must be answered *before* 1.1 starts.
2. Where the portable SKILL.md projection **lives**. The likely answer is a
   separate build-output tree (e.g. `dist/portable/<bundle>/skills/<name>/SKILL.md`)
   produced for claude.ai / Skills API packaging and *not* shipped inside the
   installed plugin — but that is a decision to make, not an assumption to inherit.
3. **How `manifest-delegate` gets fixed, and what that does to install topology.**
   There are 9 `manifest-capabilities.yml` contracts and **none is
   `manifest-delegate`** — it is in neither `DOMAIN_BUNDLES` nor
   `ADDON_BUNDLES` (`contracts.py:30` = `("manifest-i-have-adhd",)`), so it
   contributes marketplace metadata only and receives no generated files. Phase 1's
   `harness-routing.md` extract has no mechanism to be populated or
   `--check`-verified for it.

   Giving it a contract is **not** just generator plumbing:
   `load_domain_contracts()` treats any contracted bundle not in `ADDON_BUNDLES`
   as a domain and rejects it; adding it to `ADDON_BUNDLES` puts it in
   `PORTABLE_BUNDLES` and `DesiredState.all_contracts`, so adapters begin
   **installing and requiring** it — while `build_manifest_release.py` archives
   only `DOMAIN_BUNDLES`, so source/bootstrap and published-release behaviour
   diverge. This also contradicts Phase 2b's assumption that addons are uniformly
   excluded.

   Phase 0 must therefore define **two addon classes** — marketplace-only and
   portable-contracted — and for each specify loader membership, coordinator
   installation, release-archive inclusion, command-catalog behaviour, versioning,
   upgrade and rollback. `manifest-delegate`'s class, its repair mechanism, and
   its version bump are all conditional on that choice, and both source and
   published-release installs must be tested. **Until then Phase 1 cannot claim to
   repair `manifest-delegate`, and §9a's patch bump for it is provisional.**
4. **The `[[skill:…]]` grammar decision** (blocking, promoted from Phase 1).
   There are **14 colon-qualified tokens across 6 files** — not the 2 call sites an
   earlier draft assumed:
   `manifest-spec-planning/runtime/references/sub-agent-dispatch.md` (×2),
   `plan-manage` (×8), `design-validate`, `spec-audit-tasks`, `a11y-audit`,
   `ux-review`. And there are **two resolver implementations** with the same
   colon-rejecting regex: `tools/skill_ref.py:23` and
   `configs/claude/scripts/skill_ref.py:43`.
   **Neither resolver runs in production.** `tools/skill_ref.py`'s only importer is
   `tests/python/manifest_agent/test_generate_plugin_views.py`;
   `configs/claude/scripts/skill_ref.py` has no production caller;
   `_bundle_expected_views()` emits manifests and guidance, never transformed
   SKILL.md files; and marketplace entries install straight from
   `./plugins/<bundle>`. **So every `[[skill:…]]` token in every shipped skill —
   qualified or not — reaches the model as literal text today.** Extending the
   grammar would make a gate go green while changing nothing users see.

   **The real corpus is 105 tokens across 44 files — not 14.** 14 are colon-
   qualified (which additionally fail the regex); **91 are well-formed unqualified
   tokens that parse fine and still ship literal**, because nothing renders them.
   A gate that only rejects *unresolvable* tokens would pass all 91.

   **The documented convention is itself broken.** `docs/PLUGIN_RELEASE.md:63-67`
   instructs authors: *"Write `[[skill:other-name]]` in a SKILL.md body and let
   `configs/claude/scripts/skill_ref.py` render it."* Nothing calls that renderer,
   so following the repo's own guidance produces literal text in shipped skills.
   Fixing the tokens without fixing the guidance guarantees regression.

   **Therefore, Phase 0 picks one of two real options** — the extension-only
   option is removed:
   - **(a) Wire a renderer into packaging.** Build an installed-plugin SKILL
     projection that expands tokens, and repoint marketplace/release packaging at
     it. Preserves the authoring convention; adds a build stage.
   - **(b) Retire the convention.** Rewrite all 105 tokens to real qualified
     commands and rewrite `docs/PLUGIN_RELEASE.md:63-67` to forbid the syntax.
     Larger one-time edit; removes a moving part permanently.

   The gate is an **installed-artifact assertion**: **no `[[skill:` sequence
   survives in an installed bundle at all** — not merely no unparseable ones.
   Under (a) that is satisfied by expansion; under (b) by absence. Mutation-test
   both resolver implementations against one corpus regardless, so they cannot skew.

   **Ordering hazard:** Phase 1.1 vendors `sub-agent-dispatch.md` (which itself
   holds 2 tokens) into every citing bundle, *multiplying* the literals. This
   decision lands before 1.1, not after.

   **Generated artifacts carry tokens too.** The full installed corpus is **106
   occurrences across 45 files**, not 105/44: `command_catalog.py:31-58` copies
   skill descriptions verbatim into
   `manifest-workspace/skills/help/catalog/commands.json:13`. A SKILL-only
   renderer leaves that one literal. Any renderer must run **before** catalog
   generation, or the catalog must be regenerated after it.

   **Tokens must be classified by invocation context before rendering.** They do
   not all sit in prose. `tools/skill_ref.py:81` renders every token to
   `/{bundle}:{name}`, which is only meaningful as a *model* invocation — but
   tokens also appear:
   - as a command with flags in a code span —
     `docs-improve/SKILL.md:16`: `` `[[skill:parallel-agent]] --json --validate` ``
   - inside a **shell substitution** —
     `issue-triage/references/workflow.md:463`:
     `consensus=$([[skill:parallel-agent]] …)`, which renders to
     `consensus=$(/manifest-workspace:parallel-agent …)` — an invalid executable
     path that fails or silently yields empty, defaulting the consensus check.

   A token-absence gate passes in exactly that case. So: classify each of the 106
   as prose / model-invocation / shell-executable, and the isolated-install gate
   must **execute representative rendered call sites**, not merely assert the
   token is gone.

   **Default resolution for shell positions: restructure into a model
   invocation.** For the known site, `SKILL.md:50` tells the model to "execute
   each step in order in one shell", so this is model-executed shell, not human
   documentation. Packaging a standalone `parallel-agent` executable inside
   `manifest-forge` for a bootstrap-free plugin-only install is disproportionate
   to one call site — and would inherit the *entire* token-benchmark packaging
   burden below (module layout, pinned dependencies, hermetic no-network test).
   Rewriting that one step as a model invocation is bounded. Every other
   shell-position token found during classification inherits this default; a site
   where restructuring is genuinely impossible **escalates to token-benchmark
   packaging rigor** rather than being waved through.

5. **Dependency closure for the 93 cross-bundle invocations (§1.3).** Rendering a
   token is not the same as making its target installable. Classify every
   cross-bundle call as one of:
   - **(i) declared dependency — PREFERRED, empirically validated.** Add
     `dependencies` to the citing bundle's manifest.

     **Measured 2026-08-20 (live two-plugin probe).** Installing only `probe-a`,
     which declares `probe-b`, took the model-facing listing from **208 → 210
     skills (+2)**: `probe-a`'s own skill *and* `probe-b`'s. The debug log shows
     `Loaded 1 skills from plugin probe-b default directory` in the same
     enumeration pass as directly-installed plugins, with no special-casing —
     even though `installed_plugins.json` marks the entry `"auto": true`. So a
     declared dependency **does** make the dependency's skill available, not
     merely present on disk.

     **This corrects a repo-wide misreading.**
     `specs/522-apm-deploy-migration/plugin-partition.md:143-148` and
     `specs/674-plugin-architecture/spec.md:380-385` scope *"installation, not
     resolution"* **narrowly to file/path access** — `${CLAUDE_PLUGIN_ROOT}`
     resolves only to the loading plugin, so a dependency's *scripts* stay
     unreachable. Neither document tested skill availability.
     `bundle_partition.bats:131` generalised that file-access result to the
     skill case without evidence. **Its rationale must be corrected, not merely
     deleted**, or the next reader re-derives the same wrong conclusion.

     **The clean split this gives us:** cross-bundle **skill invocations** (the 93
     in §1.3) are solved by declaring a dependency; cross-bundle **file
     references** (§1.1) are not, and still require the vendoring in Phase 1.1.
     Two different defects, two different mechanisms.

     Choosing (i) still requires extending
     `schemas/manifest-capabilities.schema.json:34`,
     `src/manifest_agent/models.py:65` and `plugin_view_renderers.py:167` to
     represent and emit the field, plus version constraints and non-Claude
     behaviour.

     **Two caveats recorded honestly.** (1) Invocability in a real model turn was
     not measured — that needs a billed call; what is proven is that the skill is
     parsed, counted, and folded into the same registry that builds the listing.
     (2) **Uninstalling the dependent does *not* cascade-remove the
     auto-installed dependency** — `probe-b` survived `probe-a`'s uninstall and
     needed an explicit removal. Orphaned dependencies linger, which the
     uninstall/reconcile adapters must handle.
   - **(ii) bundle-local implementation** — duplicate or inline the capability so
     the bundle stands alone.
   - **(iii) explicit tested fallback** — the skill degrades gracefully and says so
     ("use native sub-agents when available").

   **Gate:** an **isolated install of the requested bundle plus exactly its
   declared closure** — no bootstrap, no undeclared sibling bundles — in which
   every cross-skill call either resolves or takes its documented fallback, and
   representative rendered call sites actually execute. (An earlier draft said
   "that bundle and nothing else", which contradicts branch (i), whose whole
   mechanism is auto-installing a sibling.)

   **Harness coverage is not uniform — "every supported harness" is not
   implementable as stated.** Cursor's production adapter cannot install or
   inspect a per-bundle closure: `adapters/cursor.py:246-259` reports
   *"Cursor plugin help exposes marketplace management only; no documented
   user-scope plugin inventory or activation API"*, and `:283-285` rejects any
   desired state other than the exact canonical domain set. A gate that merely
   indexes the marketplace would pass without proving anything. So: run the real
   gate on the harnesses with an inventory/activation API, and **explicitly
   classify Cursor as unverified for per-bundle closure** rather than implying
   coverage the adapter cannot deliver. Do not claim cross-harness closure until
   Cursor's native surface supports it.

### Phase 1 — Correctness (breaks nothing)

**1.1 Vendored shared references.** One canonical source outside `plugins/`; the
generator copies into each citing bundle's `runtime/references/` and `--check`
hash-verifies.

**Tool identity: a new, separately-named `tools/vendor_shared_references.py`.**
Do **not** extend `tools/vendor_bundle_dependencies.py`. That tool downloads a
PyPI sdist (PyYAML) and extracts an archive into
`manifest-code-quality/skills/smoke-manage/vendor`; merging a
network-download-and-extract safety model with a local-file-copy model in one CLI
surface is a real security-relevant coupling. The new tool takes no network
access at all.

⚠️ **False-green warning.** `vendor_bundle_dependencies.py --check` is already
CI-wired (`ci.yml:130-131`) and **passes today with zero 1.1 work done**. It is a
valid regression check that must keep passing; it is **not** evidence that 1.1
was implemented. Anything claiming 1.1 is green must cite the new tool's check.

**Targets:** **`sub-agent-dispatch.md` (the lead defect, 21 skills)**,
`antipatterns.md`, `code-constitution.md`. `command_config.yml` and
`harness-routing.md` become generated extracts.

*Accepted cost:* editing a canonical doc produces an N-way diff. Reviewers
diff-ignore generated copies. This trades silent divergence — already demonstrated
— for mechanical noise.

**1.2 Portable SKILL.md projection.** Per Phase 0's decision. Clears the 7
Constraint-2 violations.

**1.3 Repairs.**

- `issue-dev-auto`: **vendor the three merge scripts into the bundle.**

  **Premise corrected 2026-08-20.** Two earlier drafts said `pr_merge_loop.sh`,
  `merge_decision.sh` and `loop_lock.sh` "do not exist", and on that basis
  prescribed deleting the section. They *do* exist, at
  `configs/claude/scripts/`, deployed to `~/.claude/scripts/`. The original
  "not found anywhere" was a search-scope error — `find` run from inside
  `plugins/`. A capability removal justified by a false premise is not a repair,
  so that instruction is withdrawn.

  The genuine defect is the **`command_config.yml` class**: bootstrap-only, and
  therefore unreachable under the plugin-only install that Constraint 1 makes
  primary. Remedy: vendor into `manifest-forge/runtime/bin/` (already a declared
  `forge-bin` component), convert the config dependency
  `automation_authors.yml` to `runtime/config/automation_authors.json` — the
  bundle avoids an ambient YAML dependency, which is why every other vendored
  forge config is JSON — and patch only the vendored copy to read it, leaving the
  bootstrap copy on YAML.

  **It is FOUR scripts, not three.** `pr_merge_loop.sh:392` hard-calls
  `${SCRIPT_DIR}/verification_gate.sh` from `cmd_tick`'s `run-gate` branch.
  Omitting it would leave the Tier-1 verification gate unreachable through
  `tick` — i.e. the `merge` action could never satisfy its own precondition —
  which is the same reachability defect this repair exists to fix. Vendor
  `pr_merge_loop.sh`, `merge_decision.sh`, `loop_lock.sh` **and**
  `verification_gate.sh`. Their remaining dependencies (`git_ops.sh`,
  `git_platform.sh`, `audit_log.sh`) are already present in `runtime/bin`.

  *Process note:* the three-script list came from the same flawed audit as the
  "not found anywhere" claim. **Enumerate a script's transitive `SCRIPT_DIR`
  callees before vendoring**, rather than trusting a hand-written list — the
  bundle-local link checker (§4 1.4) must cover script-to-script calls, not only
  SKILL.md references.

  **It is now five files, and the fifth proves the process note's point.**
  `pr_merge_loop.sh` was split on the gh-I/O seam to clear the 600-line ceiling,
  producing `pr_merge_loop_gh.sh` — sourced at `pr_merge_loop.sh:62`. It is safe
  only because the split created it *inside* the bundle, not because any
  transitive-closure enumeration caught it. The link checker must cover
  `source`/`.` directives, or the next such dependency is missed the same way.

  **The two copies have no drift detection.** `configs/claude/scripts/pr_merge_loop.sh`
  and the vendored copy are independently maintained, correctly diverged on
  `STATE_DIR` and `AUTHORS_FILE` — but with no digest, no `--check`, and no
  canonical-source declaration pairing them. That is a *second, ungoverned*
  vendoring pattern sitting alongside the governed one Phase 0 item 1 is
  designing. Phase 0 must state whether script vendoring is absorbed into the same
  canonical-source+digest mechanism or stays permanently ad hoc; "two patterns,
  one of them undetectable" is not an outcome to arrive at by default.

  **Safety hardening remains a separate spec, and is still required.** The loop
  performs an irreversible admin squash-merge to main after separately-collected
  CI, review and consensus signals, and no document defines its state-machine
  invariants. That spec must specify fail-closed preconditions, an atomic re-read
  of all signals immediately before merge (they are gathered separately, so a
  stale-signal TOCTOU window exists), crash-recoverable locking, idempotent
  retries, branch-protection and permission checks, behaviour when the branch
  changes between decision and merge, post-merge failure handling, and
  concurrency/crash mutation tests. Vendoring fixes reachability; it does not
  make the automation safe, and Phase 1 makes no claim that it does.

  **Update 2026-08-20 (CDDL QA-critic finding): Phase 1 ships the read-only
  subset only, `merge` hard-gated.** The gap above was not theoretical.
  `loop_lock.sh`'s concurrency lock is known-inert in production: GitHub's
  `--add-label` only attaches pre-provisioned labels, and
  `configs/claude/config/labels.yml:58-61` provisions only the static
  `loop-active`, never the dynamic `loop-active:<epoch>:<token>` lease the lock
  actually requests, so no lease is ever really taken. The test that had been
  passing for this used a seam that accepted arbitrary label names as if they
  were pre-provisioned — a false green. Six further high findings remain open
  (no global serialization of merges to main, no `--match-head-commit` on the
  merge, `sink_reverify` not rechecking `reviewDecision`, and more). Given
  Constraint 1 — the plugin-only install is primary, and external plugin-only
  users are its consumer — shipping a reachable admin-squash-merge behind a
  lock that does not work is not acceptable. Phase 1 therefore vendors and
  ships the **read-only subset only**: `list-managed`, `signals`, `decide`,
  `address-cycle`, and `tick` up to but excluding the merge sink all work
  normally. `cmd_merge` in the vendored copy refuses unconditionally — not
  behind `PR_MERGE_LOOP_APPLY`, which is not an env toggle for this gate —
  pending the separate safety spec above. The decision logic is not deleted,
  only the sink; the operator/bootstrap copy was believed unchanged and out of
  scope for this repair at the time this paragraph was written — see the
  "third CDDL developer-reviewer finding" correction below the "Fix (this
  repair)" bullets: that turned out to be false too, in the opposite direction
  from the tick/run correction just above (a regression, not a no-op).

  **Correction, 2026-08-20 (second CDDL QA-critic finding, same day): the
  "tick ... works normally" claim above was false the moment it was written.**
  The `cmd_acquire` fail-closed fix that made this update necessary
  (`label_op add ... || true` → fail on a failed add) did not only close the
  lease-integrity hole — it also made `cmd_tick` (and therefore `cmd_run`, and
  the `tick <pr>` call `issue-dev-auto/SKILL.md` documents the loop making)
  **dead on arrival**: since `label_op add` unconditionally fails against real
  GitHub (the same provisioning gap this update describes), `loop_lock.sh
  acquire` returned nonzero for every PR, every time, and `cmd_tick` treated
  *any* acquire failure as `"#$pr locked — skipping"` — never reaching
  `cmd_signals`, `merge_decision.sh`, the verification gate, or dispatch. The
  read-only subset genuinely worked normally (`list-managed`/`signals`/`decide`/
  `address-cycle` never touch the lock); `tick` and `run` did not — they always
  returned `skip` against a real backend, contradicting this section outright.

  This was **not caught by tests** for the identical reason as the original
  finding: `tests/bats/pr_merge_loop.bats`'s lock stub (used by every
  `tick`/`run` test, vendored copy included) accepted `add` for any label name
  unconditionally — the same false-green shape `loop_lock.bats` had just been
  fixed to stop using, simply not propagated to the suite that actually
  exercises `tick`/`run` through the lock. This is the **second instance of the
  same defect class** in this spec's history (the first being the original
  finding this section documents), and it hid the dead-on-arrival regression
  for as long as it existed.

  **Fix (this repair): the lock is now proportionate to what it protects.**
  Merge is hard-gated (exit 78, unconditional), so this lock no longer guards
  anything irreversible — its only remaining purpose is avoiding a duplicated
  (expensive) run-gate pass, not preventing damage. `loop_lock.sh acquire` now
  returns two distinct nonzero codes: **1 (CONTENDED)** — a live, non-stale
  lease already recorded for someone else, a lost add-race, an inconsistent
  post-add re-read, or same-host `flock` contention — which still blocks;
  **2 (DEGRADED)** — the lease could not even be *attempted* (the backend
  rejected the add, e.g. the unprovisioned dynamic label case this section
  describes) — which is not evidence of contention. `cmd_tick` now proceeds to
  real dispatch (and logs the degraded condition loudly) on 2, and only skips
  on 1. Net effect, precisely stated:
  - **Work normally, unconditionally:** `list-managed`, `signals`, `decide`,
    `address-cycle` (never touch the lock).
  - **Degraded but functional:** `tick` and `run`. They compute signals, run
    the merge decision, run the Tier-1 verification gate, and dispatch
    (`revise`/`wait`/`update-branch`/`hand-human`/attempt-`merge`-which-hard-
    gates) correctly — but the cross-host mutual-exclusion property the lock
    is documented to provide (research.md R4) was **not actually enforced**
    against other hosts/runners in production, since the dynamic lease label
    could never attach. Same-host contention (`flock`) and any lease that *is*
    genuinely on record still block correctly.
    **Superseded 2026-08-20 by the self-provisioning fix in the third
    correction below** — the lease label is now created before it is attached,
    in both copies, so cross-host mutual exclusion is enforced again. This
    bullet records the state between the two same-day corrections; it is not
    the shipped behaviour.
  - **Unaffected, unchanged:** `merge` stays hard-gated (exit 78,
    `PR_MERGE_LOOP_APPLY` is not a toggle for it) — that gate is unconditional
    and this repair does not touch it.
  - `tests/bats/pr_merge_loop.bats`'s lock stub now faithfully rejects `add`
    (matching `loop_lock.bats`), and carries dedicated vendored-copy regression
    tests proving both the degraded-proceed and genuinely-held-blocks paths.

  **Correction, 2026-08-20 (third CDDL developer-reviewer finding, same day):
  "the operator/bootstrap copy is unchanged and out of scope" was also false.**
  `configs/claude/scripts/loop_lock.sh` received the *same* lock-ownership
  hardening as the vendored copy in this repair — the dynamic
  `loop-active:<epoch>:<owner>` lease name, per-owner tokens, and the
  post-add re-read that breaks the check-then-add race — because an earlier
  pass in this repair applied that fix to both copies together (they were, at
  that point, still meant to converge). Only the *compensating* half — the
  `cmd_acquire` fail-closed behaviour (exit 2/DEGRADED) plus the matching
  `cmd_tick` proceed-on-DEGRADED logic documented above — landed in the
  vendored copy alone. That was a **regression**, not a no-op: before this
  repair, the operator copy requested the static `loop-active` label, which
  `labels.yml` *does* provision, so `label_op add` succeeded and the lock
  genuinely worked (with the narrower, already-known TOCTOU race the header
  comment describes). After it, the copy requested the same unprovisioned
  dynamic label the vendored copy does, `label_op add` failed every time, and
  — lacking the CONTENDED/DEGRADED exit-code split — its `cmd_tick` could not
  distinguish that from genuine contention and treated every failed acquire as
  `"#$pr locked — skipping"`. Net effect at that moment: operator `tick` and
  `run` skipped **100% of PRs**, unconditionally, against a real backend.

  **RESOLVED 2026-08-20 (same day, fourth finding). The paragraphs above are
  the audit trail, not the shipped state.** The root cause was never the
  ownership hardening — it was that `labels.yml` *cannot* provision this name
  (the `:<epoch>:<owner>` suffix is unbounded, generated fresh per
  acquisition, so no static registry entry could ever cover it), and a
  GitHub/GitLab `--add-label` only ever attaches a label that already exists.
  The fix is therefore **self-provisioning**, applied to *both* copies
  (`configs/claude/scripts/loop_lock.sh:105-125` and
  `plugins/manifest-forge/runtime/bin/loop_lock.sh`): `label_op add` creates
  the dynamic lease label via `git_ops.sh label-create --force` — idempotent,
  so a retry or a racing runner's identical create is harmless — immediately
  before attaching it. If creation itself fails (no `label-create` permission,
  API error), the add fails too and the caller sees a DEGRADED acquire rather
  than a false success. The "can never attach" premise no longer holds
  anywhere in this section.

  **The DEGRADED-proceed fix is still deliberately NOT ported here — and that
  asymmetry is the shipped design, not a deferral.** The vendored copy can
  safely proceed on a DEGRADED (unattempted) lease because its `cmd_merge` is
  hard-gated to exit 78 unconditionally — nothing irreversible is behind the
  lock any more. The operator copy's `cmd_merge` is **not** gated: it performs
  a real `gh pr merge --admin`, so proceeding blind could let two concurrent
  loops merge the same PR.

  With self-provisioning in place, the DEGRADED branch is no longer the
  everyday path — it now means what it says: the lease could not be
  *attempted* (label creation itself failed). The operator copy therefore
  **refuses to proceed and fails loudly with exit 12** rather than collapsing
  into a benign `skip`. That distinction is the point: a silent exit-0 skip
  would make exit-code-based monitoring read success while no signal
  collection, merge decision, or verification gate ever ran. Precisely:

  - `loop_lock.sh acquire` → **1 = CONTENDED** (a live lease held elsewhere, a
    lost add-race, or same-host `flock`); **2 = DEGRADED** (unattemptable).
  - Operator `cmd_tick`: on 1, `skip` + exit 0 (correct — someone else holds
    it); on 2, a loud `err` naming the condition and **exit 12**, propagated to
    the caller (`pr_merge_loop.sh:404-436`, `:497`, `:581`).
  - Vendored `cmd_tick`: on 2, still dispatches real work, because its merge
    is hard-gated.

  **No tests are skipped.** An earlier draft of this section said
  `tests/bats/pr_merge_loop.bats` carried a `FINDING (2026-08-20,
  faithful-seam propagation)` comment ahead of three operator `tick` tests it
  `skip`ped; that is stale. The file instead asserts the behaviour above,
  including `REGRESSION: DEGRADED lease (label backend rejects add) -> tick
  fails loudly (exit 12), not a silent skip`, the benign CONTENDED exit-0
  path, and the vendored copy's degraded-proceed path. The companion safety
  spec is no longer load-bearing for this defect: nothing here is left
  broken-but-safe.
- `manifest-workspace/hooks/manifest-hooks.json`: **delete the dead catalog and
  mark both capabilities unavailable.** Not "rewrite to the real schema" — that
  was the same underspecified coin flip as the merge loop. The file is an advisory
  catalog with *invented* events (`context-budget`, `task-completed`) that have no
  command handlers; `session-checkpoint` has no executable hook script, and
  `configs/claude/prompts/context_monitor.md` states outright that no automatic
  trigger exists. "Rewriting to the real schema" would require inventing trigger
  semantics, so a mechanical implementation lands either inert or firing state
  writes on an over-broad lifecycle event. Reinstating either hook is a separate
  spec that must name the exact native event, command, inputs/outputs, fail-open
  behaviour, idempotency, rate limiting, teardown, and mutation tests.

  **Deleting the file alone breaks the build.**
  `manifest-workspace/manifest-capabilities.yml:27-29` declares the component
  (`id: manifest-hooks`, `path: hooks/manifest-hooks.json`) and
  `validate_component_assets()` rejects any declared component whose path is
  absent. The full migration is: remove the component from the contract, delete
  the file, regenerate views, update `docs/PLUGIN_CAPABILITY_MATRIX.md`
  expectations and the tests that assert this component exists, and record the two
  retired capabilities in an explicit changelog **tombstone** — the schema can
  express "unsupported" only on a component that still has a required path, so
  removal makes the matrix row vanish silently otherwise
  (`PLUGIN_CAPABILITY_MATRIX.md:188` is the row that disappears).

  **Tombstone format, location and enforcement.** The entry goes in the existing
  top-level `CHANGELOG.md` under a `### Retired capabilities` heading, one line
  per capability naming the bundle, the capability id, and the reason.
  **Enforced:** extend the same regression test that proves the path is neither
  declared nor emitted so it *also* asserts a matching tombstone line exists for
  each removed capability id. §9a and R8 refuse unenforced documentation promises
  elsewhere; this one gets the same treatment.
- Strip `_manifest` from both `manifest-ops` hook files (Constraint 2 portability;
  see §1.2 caveat — this does not restore Codex parity).
- `docker-compose-commandments`: `scripts/` → `runtime/bin/`, `config/` → `runtime/config/`.
- `upload-to-stitch` / `manage-design-system`: remove the phantom `--api-key` flag.
- **`token-benchmark`: decide explicitly — package or retire.** Critical 7 is
  listed as caught by the link checker, but no repair was assigned, so the new
  gate would sit permanently red. The shipped skill contains only its SKILL.md
  and metadata while invoking `tests/token_benchmark/harness.py`, fixtures and
  results under `tests/`, and `docs/TOKEN_BENCHMARK.md` — none present in an
  individual `manifest-workspace` install.

  **Decision: package it.** Retiring would delete
  `/manifest-workspace:token-benchmark`, which Constraint 3 forbids in Phase 1 —
  so "package or retire" was not actually a free choice, and an earlier draft
  offering both while saying "do not leave this to an implementer" contradicted
  itself.

  **Packaging is deeper than "harness and fixtures".** The skill's default path
  runs `uv run --group benchmark` (SKILL.md:84-97), and that dependency group
  exists only in the repository `pyproject.toml:68-73`; `harness.py:35-36`
  inserts `REPO_ROOT` into `sys.path`, and imports `benchmarks.py`, `scorer.py`
  and `reporter.py` from `tests/token_benchmark/`. The workspace contract
  declares neither `uv` nor those SDK dependencies. Packaging must therefore
  specify the complete module layout, a pinned standalone dependency strategy,
  and either remove or explicitly declare the `uv` requirement.

  **Test the default path, not an easy one.** A pass using `--cli-only`,
  `--report-only` or `--help` proves nothing: exercise the default/API path,
  CLI-only, and report-only **from a copied bundle with the repository absent and
  the network disabled**.

  **Mutable state, including fixtures.** Results, reports *and fixtures* go to a
  cross-harness XDG data root (with an optional Claude-specific override), never
  under the versioned install path, which is replaced on plugin update. See the
  security requirement below.

  **Fallback:** if Phase 0 finds packaging infeasible, retirement moves to Phase
  2b with the versioning and tombstone from §9a. It does not happen in Phase 1.

  **Security — fixture sync can commit credentials (fix regardless of this
  spec).** `--sync-fixtures` copies the live `~/.claude/settings.json` into a
  tracked fixture tree (`harness.py:37`, `:510-552`), and the scrubber
  `_scrub_fixture_pii` (`:488-507`) strips only ANSI escapes, the home path and
  the username — it does **not** redact values under `settings.json`'s `env`
  mapping, a supported place for API keys. SKILL.md:111-114 then instructs users
  to stage that tree. Required: stop copying `settings.json` wholesale, allowlist
  only the files the benchmark actually reads (`benchmarks.py:34-38` reads
  `CLAUDE.md` and `GEMINI.md`), add secret-redaction tests, and drop the
  fixture-commit instruction. **This is a live defect in shipped code, not a
  Phase 1 nicety.**

**1.4 CI gates.**

- ~~`claude plugin validate --strict` per bundle~~ — **PERMANENTLY OUT OF SCOPE
  (2026-08-26).** The `claude` CLI is not available in CI: `grep -c 'claude
  plugin' ci.yml` was 0 before this feature, so a gate phrased this way is
  either unrunnable or **skips green**, and a skip that renders as a pass is the
  exact false green this phase exists to remove. Recorded at
  `.github/workflows/ci.yml:523-528`, where the bundle-partition job states the
  same reasoning as its own justification for being pure python3 + bats.
  (For the record: 10/10 bundles currently fail it on one benign warning each —
  9× `compatibility`, 1× missing author — so wiring it would also require
  silencing warnings before it could ever be green.)
- **Bundle-local link checker**: fail when a SKILL.md cites a path absent from its
  own bundle. Catches criticals 1, 2, 4, 6, 7 of the 8 enumerated in §10 —
  **5 of 8**, not 6. (An earlier draft claimed 6 by counting critical 8; see the
  next gate for why that is wrong.)
- **Token gates — two separate checks** (implements Phase 0 item 4). An earlier
  draft specified one parse-or-resolve gate scoped to 14 tokens; that would pass
  the 92 well-formed unqualified tokens and the generated-catalog copy while they
  still ship literal.
  1. **Source grammar check** — only if Phase 0 chose option (a) and tokens are
     retained in source. Mutation-tested against both resolver implementations
     with one shared valid/malformed corpus, so they cannot skew.
  2. **Packaged-artifact check** — assert **zero `[[skill:` sequences in every
     packaged file type**, Markdown *and* generated command catalogs *and*
     vendored references. Baseline to drive to zero: **106 occurrences across 45
     files**.

     **OUTCOME 2026-08-27: Phase 0 item 4 decided as option (b) — the
     convention is RETIRED.** All 106 tokens across 45 files were rewritten to
     qualified `bundle:skill` commands, `PLUGIN_RELEASE.md` now forbids the
     syntax, and the gate is live at zero in
     `tests/python/test_skill_token_ratchet.py`. Option (a)'s source grammar
     check (item 1 above) is therefore **permanently out of scope** — it was
     conditional on tokens being retained in source, and none are.
- **Isolated single-bundle install gate** (implements Phase 0 item 5) — install
  one bundle alone and assert every cross-skill call resolves or takes its
  documented fallback.

  **It must be a real `claude plugin install`, and it does not go in CI yet.**
  Fixture simulation is disqualified by this spec's own Cursor argument — a gate
  that only indexes the marketplace proves nothing, and the sole existing
  precedent (`tests/python/manifest_agent/_plugin_view_fixtures.py::build_fixture_repo`)
  is exactly that: a filesystem simulation that never invokes the CLI. But a real
  install in CI needs headless auth, a sandboxed HOME, and marketplace network
  access, none of which exists today. So this lands as a **documented local
  pre-release gate**, using the method already exercised twice in this spec's own
  probes: stand up a local marketplace, install, measure the listing via
  `claude -p … --debug-file` with a deliberately-invalid model id (errors after
  skill-loading, before billing), then uninstall and verify cleanup against a
  pre-probe snapshot. CI wiring is deferred and tracked as R10 — not silently
  assumed.
- Lint for fully-qualified `agent:` names — a bare name silently resolves to
  general-purpose with no error.

**1.5 `disable-model-invocation: true`** — the only frontmatter field measured to
shrink the listing (−235 chars/skill). **Scope narrowed: it may be applied only to
a wrapper whose always-installed hook fully replaces its model-invoked behaviour.**

An earlier draft claimed "the Skill tool is never involved, so the flag is safe"
for four skills. That is wrong for at least two of them, and the mistake is a
user-visible capability regression:

- `version-pin` is an on-demand **auto-fixer**; its hook is `mode: advisory` and
  warn-only, and never edits. Disabling model invocation means "pin these
  versions" no longer reaches the thing that can do it.
- `docker-compose-commandments` is a user-requested audit-and-remediate workflow;
  its hook only observes edits.
- `issue-sync-commit` / `issue-sync-pr` hooks are **opt-in and default off**, so
  for most installs the model path is the only path.

**Implementation must therefore enumerate candidates and prove, per skill, that an
always-installed hook delivers the full behaviour** before setting the flag. If no
skill clears that bar, 1.5 delivers nothing and is dropped — say so rather than
applying the flag for the token saving. *Cost where it does apply:* loses
out-of-band manual invocation.

**OUTCOME 2026-08-21: no skill cleared the bar. 1.5 delivered nothing and is
dropped, exactly as the paragraph above requires be said plainly.** Measured
against `main` in the working tree: **zero** `disable-model-invocation`
additions. The flag's only occurrence in the repo,
`plugins/manifest-i-have-adhd/skills/i-have-adhd/SKILL.md:4`, predates this
work and was not touched — and sits on an **addon**, not on any of the 8
domain bundles, so it could not have moved the domain listing even if it had
been applied here. The −235 chars/skill saving in §6's table remains a
*measurement*, not a *delivery*. Anything downstream that treats 1.5 as
shipped (see the §9a correction) is wrong.

### Phase 2a — Budget (non-migrating, but NOT compatibility-free)

**Correction.** An earlier draft called this "zero compatibility surface". That is
wrong by this repo's own policy: `docs/PLUGIN_RELEASE.md` classifies *"a skill
added or removed, **or any description change**"* as a **minor** bump, because
both move the always-on token cost, which is user-visible. Both items below are
therefore versioned changes requiring minor bumps. They are "non-migrating" — no
skill changes bundles, so no `renames` map is needed — not "non-breaking".

- **2a-i · Trim descriptions.** Manifest: 197 mean / 200 median. Best-in-class
  (superpowers 6.3.0, 14 skills): **133 mean / 105 median**. Target the mean;
  narrow skills keep keyword-rich descriptions — trimming is not uniformly safe
  and would break their triggering. Lockstep bump per §9a.
  **Required gate:** a per-skill **positive/negative trigger corpus** for every
  touched skill, run before and after the trim. The spec cannot both admit that
  trimming breaks triggering and ship it without a recall test.

- **2a-ii · Relocate ~21–26 micro-lesson skills** into `references/` of a thematic
  parent. **This removes a public command.** Qualified names are the only way to
  reach a skill — `docs/PLUGIN_RELEASE.md`: *"reachable **only** as
  `<bundle>:<name>` … There is no bare alias and no fallback"* — so relocating
  `/manifest-ops:cache-warm-oob` into a reference deletes that command, and
  reachability then depends on a parent skill both triggering *and* electing to
  read the reference. Required before any relocation lands:
  1. An **enumerated skill→parent mapping** for all 21–26, not a count.
  2. A **trigger regression corpus**: for each relocated skill, natural-language
     prompts that must still reach the content via the parent.
  3. A **tested compatibility shim for every relocated command**, and the shim
     **must carry `disable-model-invocation: true`**. This is the crux: the
     always-on listing is *name + description* (§6), so a plain shim keeps the
     entry and **2a-ii would save literally nothing** — bodies were never in the
     listing. `disable-model-invocation: true` is the one measured lever
     (−235 chars/skill) and it removes the model-facing entry while leaving
     `/manifest-ops:cache-warm-oob` user-invocable. Without it there is no reason
     to do 2a-ii at all.

     **Portability carve-out.** `disable-model-invocation` is *not* in the open
     Agent Skills field set (Constraint 2), and Phase 1.2 strips it from the
     portable projection — so requiring it in "both the installed Claude plugin
     and the portable projection", as an earlier draft did, was unsatisfiable by
     construction. The flag lives **only in the Claude-native projection**.
     Portable shims need separate semantics using allowed frontmatter only, and
     the two artifacts are verified against distinct harness contracts.

     **The shim itself always ships; only the flag is Claude-only.** An earlier
     draft allowed omitting the portable shim and documenting the skill as
     Claude-only — that breaks Constraint 3. `_generic_harness_surface()`
     (`plugin_view_renderers.py:280-290`) publishes the same skill set to Codex,
     Cursor, Devin and Antigravity, so these commands are **already public
     portable surface**; dropping a shim there is an unversioned cross-harness
     command removal hiding inside a budget phase. The portable shim therefore
     always ships.

     **But shipping a shim is not the same as making it model-visible, and the
     spec must not conflate them.** Each harness governs implicit visibility
     separately: Codex reads `agents/openai.yaml` (`cache-warm-oob` is already
     `allow_implicit_invocation: false`) against the
     `codex_implicit_invocation_allowlist` in `configs/claude/config/skill_policies.yml`,
     whose own prompt budget is capped at 2% of context / 8,000 chars. Forcing
     21–26 shims into that catalog would blow Codex's budget to save Claude's —
     defeating the objective.

     **Rule:** a portable shim preserves the **explicit** `$bundle:skill` command
     on every harness, and inherits that harness's *existing* implicit-visibility
     policy — it does not join any implicit catalog. Measure listing impact per
     harness independently. If a portable forwarding shim cannot be proven for a
     given skill, that skill does not relocate in 2a — it moves to 2b.
  4. Lockstep bump per §9a; every shim listed in the changelog.

  **Quantified exit criterion.** 2a must demonstrate a measured net listing
  reduction — via §6's paired-run method, not `claude plugin details` — of at
  least **1,200 chars** across 2a-i and 2a-ii combined. If the measurement comes
  in under that, the relocation half is not worth its migration cost and should
  be dropped rather than shipped for appearances.

  If (1)–(3) cannot be satisfied for a given skill, it stays where it is.

### Phase 2b — The 1.0 split (breaking; promote to Speckit)

Per [docs/SPEC-SYSTEMS.md](../../SPEC-SYSTEMS.md), a change of this size belongs in
`specs/` under the gated lifecycle. This document is the design record; 2b's
implementation runs through `/speckit-specify`.

**What it buys, stated honestly.** §5.5 rejects the 34-bundle restructure because
catalog-wide totals stay flat under a split-only mechanism. That property holds
here too, by construction: moving a skill between bundles changes *which plugin
bills the token*, not whether it is billed. **Phase 2b buys per-persona install
ergonomics — a Python-only user installing ~55 tok instead of ~1,315 — not
aggregate budget reduction.** The aggregate win comes from Phase 2a.

**Design principle: one bundle = one install decision.** People install for a
reason — "I write Python", "I manage PRs". `manifest-code-quality` bundles 24
skills spanning Go, Terraform, Node, Python, shell, data pipelines and CLI auditing
because they are conceptually code quality, not because anyone wants all seven.

*Counter-evidence to weigh:* superpowers ships 14 topically-coherent skills at 439
tok and is widely adopted, so the principle is not "smaller is always better" — it
is "coherent with an install decision". Cut on language/tool boundaries, not
arbitrarily.

**The migration mechanism is an open problem — `renames` does not solve it.**
The marketplace `renames` map rewrites one old plugin slug to one new plugin slug.
This split keeps `manifest-code-quality` alive while distributing 7 of its skills
across 5 new bundles, so there is no one-to-one mapping to express: the old slug
cannot point at every target, and it cannot be retired without orphaning the 17
skills that stay. Existing installs will therefore **not** acquire the new bundles
automatically, and their old qualified names (`manifest-code-quality:python-refactor`)
disappear regardless.

Phase 2b must therefore design and prove a real upgrade path before it starts.
Candidate mechanisms, none yet validated:

1. **Transitional compatibility skills** under the old qualified names in
   `manifest-code-quality`, each a thin stub, plus `dependencies` on the new
   bundles so installing the old one pulls the new ones. (`dependencies` is
   confirmed to auto-install its target — §5.2.)
2. An explicit **reconciliation command** the user runs once.
3. Accept the break, document it loudly, and bump major.

**Acceptance test:** upgrade from the currently *published* installed state — not
from a fresh install — and verify every previously-working qualified command
either still resolves or is documented as removed.

**The 5 new bundles do not fit the current topology.** `DOMAIN_BUNDLES`
(`src/manifest_agent/contracts.py:20`) is a hardcoded tuple of exactly **8**
names, and `load_domain_contracts()` rejects contracts outside it;
`tools/check_plugin_runtime_paths.py:26` keeps a second copy. So each new bundle
must be classified **before** 2b starts, and neither option is free:

- **Domain-backed** → `DOMAIN_BUNDLES` grows to 13 in both copies, and everything
  that iterates it changes: contract loading, generation, release archives and
  indexes, command catalogs, reconciliation receipts, uninstall adapters, and the
  `_release_version()` lockstep (now 13 bundles that must agree).
- **Addon** → excluded from coordinator installs and releases, so the moved skills
  simply *disappear* for those users.

Work: classify each new bundle; make the corresponding topology changes; move the
7 skills; ship the chosen migration mechanism; major bump + changelog; test
rollback and upgrade from every published version.

---

## 5. Rejected alternatives

### 5.1 Additive thin bundles ("Freeze-and-Fork")

Publish `manifest-python` etc. as additional entries projecting the *same* source
files. **Rejected, and the rejection survived a dedicated refutation lens.**

- `generate_plugin_views.py:181-186` raises `domain bundles cannot be addons` and
  requires `source == ./plugins/{name}`. *(Our own code — a fence, not a wall. Not
  the blocking reason.)*
- **Blocking, now empirically confirmed.** A live two-plugin install (2026-08-19
  R1 probe) measured: baseline 207 skills / 50,826 chars; +plugin-alpha 208 /
  51,090; +plugin-beta shipping a **byte-identical** SKILL.md under the same
  directory name 209 / 51,353. The debug log shows two independent
  `Loaded 1 skills from plugin …` events with no cross-plugin comparison. **No
  dedup by name, content hash, or source path.**
- The **same-name / different-description** variant measured identically (209 /
  51,354) — so independently drifted copies do not even collide cleanly; they
  silently coexist and compete for trigger selection. This is the worse failure mode.
- *Escape hatches foreclosed:* a differently-named delegating skill still costs a
  full listing entry (the probe's divergent-description case proves renaming
  changes nothing) and cannot reach another plugin's files anyway (§5.2). No
  metadata-based mutual exclusion exists — `marketplace.json` entries carry only
  `{category, description, homepage, keywords, name, source, version}`, and
  `dependencies` force-installs its target, the opposite of exclusion.
- *Not verified:* the interactive `/` menu was not observed directly (no TTY in the
  probe). It reads the same registry, so dedup there is implausible — but that is
  inference, not measurement.

### 5.2 `manifest-core` + plugin `dependencies`

`dependencies` is real — it auto-installs its target and fails loudly when missing
— but **cannot share files**. Every path variable (`${CLAUDE_PLUGIN_ROOT}`,
`${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_PROJECT_DIR}`,
`${CLAUDE_PLUGIN_OPTION_*}`) resolves only to the current plugin.
`../../<dep>/<version>/` resolves physically but needs a version string unknowable
at authoring time. Moves the budget by exactly zero.

### 5.3 `paths:` / `when_to_use` / `user-invocable` as budget levers

Measured at zero or negative. See §6.

### 5.4 Widening `subagent_model_default.py` `DISPATCH_TOOLS` to include `Skill`

`decide()` reads `subagent_type` and `model` from `tool_input` — Agent-tool fields.
The Skill tool's schema has `skill` and `args`. Adding `"Skill"` unchanged injects
a `model` key the schema does not define, turning a fail-open hook into one that
may fail **closed on every skill dispatch**. The real fix reads the skill's
`agent:` frontmatter and resolves that agent. Out of scope.

### 5.5 Fine-grained 34-bundle restructure in one step

Best on budget and adoption lenses, worst on feasibility (1.5/10). Its own
arithmetic showed catalog-wide totals stay **flat**; only per-persona installs
improve. Phase 2b takes the same direction at a defensible size — and §4 states
that flat-total property applies to 2b as well.

---

## 6. Empirical basis

Claude Code 2.1.237, real skill listing, paired back-to-back runs, each reproduced
2–3×.

| Field | Effect on always-on listing |
|---|---|
| `paths:` globs | **zero**, matching cwd or not (3×) |
| `user-invocable: false` | **zero** — affects only the `/` menu |
| `context: fork` + `agent:` | **zero** — execution semantics only |
| `when_to_use` | **negative** — grows listing 1:1 with length |
| `disable-model-invocation: true` | **−1 skill, −235 chars** (3×) |

**`claude plugin details` is a raw content-length sum** — blind to every field
above and to `skillListingBudgetFraction`. It cannot verify a budget claim. All
token figures in §1.4 are content sums: sound for comparison, not authoritative.

Also verified: `agent: <bare-name>` silently falls back to general-purpose; a
forked skill's `model:` is not honored (0/4); `claude plugin list --json` reports
`enabled: true` for plugins that failed to load, so health tooling must read
`errors[]`.

---

## 7. Risks and open questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | ~~Double-billing inferred, not tested~~ | **CLOSED 2026-08-19.** Live two-plugin install confirmed it (§5.1). |
| R1b | ~~Whether a declared dependency makes the dependency's *skill* resolve~~ | **CLOSED 2026-08-20.** Live probe: 208 → 210 skills installing only the dependent. Branch (i) is viable and preferred (§4 Phase 0 item 5). |
| R10 | The isolated single-bundle install gate cannot run in CI — needs headless auth, sandboxed HOME, marketplace network access | Runs as a documented **local pre-release gate** using the probe method in §5.1; CI wiring deferred, not assumed |
| R9 | Auto-installed dependencies are **not** cascade-removed when the dependent is uninstalled — they linger as orphans | Uninstall and `deploy-reconcile` adapters must detect and offer to remove orphaned auto-installed dependencies; add a regression test |
| R2 | No test today covers vendored-reference growth. `context_budget.bats` scopes only SKILL.md frontmatter; the string `on_invoke` does not exist in this repo | Add a new assertion — this is net-new work, not an edit |
| R3 | `tests/python/manifest_agent/` is 65 files / 439 test functions; they share `_plugin_view_fixtures.py::build_fixture_repo` | First unit of work is redesigning that fixture harness, not "extend `--check`" |
| R4 | Vendoring and portable projections compose multiplicatively in `_bundle_expected_views()` | Measure generated-output size after 1.1 before starting 1.2 |
| R5 | `command_config.yml` as a generated extract conflicts with its role as live input to `parallel_agent.py`, which hardcodes `~/.claude/config` | Document which path wins; bootstrap must agree |
| R6 | `manifest-graphify` provenance unknown | Identify before acting |
| R7 | Phase 2a description trimming can break triggering for narrow skills | Trim broad skills only; narrow ones relocate instead |
| R8 | **Every changed bundle needs a version bump or the fix reaches nobody.** `docs/PLUGIN_RELEASE.md`: *"`plugin.json` is the SOLE source of the version… it wins at install time"*, and `claude plugin update` no-ops when the version is unchanged — installed users execute versioned cached copies. Separately, `manifest-release.yml` fires only on push-to-main, requires all 8 domain bundles' `bundle.version` byte-identical (all `0.2.0` today), and silently logs-and-skips if already published | Ship a **version matrix** (§9a) covering every changed domain bundle **and every addon** at the correct level. **Correction:** an earlier draft scoped this to the secondary APM channel only, claiming primary installs read `./plugins/{name}` directly. That is wrong — primary plugin users are equally affected. `manifest-delegate` is an independent addon outside the 8-bundle lockstep, so Phase 1's `harness-routing.md` fix strands its users unless it is bumped explicitly |

**Already resolved, no action:** `adversarial-design-loop`, `manifest-docker` and
`manifest-graphify` are absent from both `plugins/` and `marketplace.json` at
`ad1faee3`. They persist only as **stale installs** in local caches — a user-side
`claude plugin uninstall`, not a repo change.

## 8. Verification

- Every Phase 1 repair gets a regression test that **fails before the fix**
  (mutation-verified — flip the source, watch it fail, restore).
- ~~`claude plugin validate --strict` green on all bundles.~~ Superseded: see
  §4 1.4 — permanently out of scope, because the CLI is absent in CI and the
  check would skip green rather than fail honestly.
- Link checker green; deliberately break one reference and confirm it fails.
- `codex exec` startup produces no plugin-parse errors.
- Re-measure the listing after 1.5 via §6's paired-run method, **not**
  `claude plugin details`.

## 9. Effort

| Stage | Estimate |
|---|---|
| Phase 0 (design the two mechanisms) | 1–2 sessions |
| Phase 1 | 8–10 sessions |
| Phase 2a | 3–4 sessions (raised: 2a-ii now needs a mapping + trigger corpus) |
| Phase 2b | 12–16 sessions (Speckit) — excludes designing the migration mechanism |

## 9a. Version matrix (required by R8)

Per `docs/PLUGIN_RELEASE.md`: patch = body/reference edit; minor = skill
added/removed **or any description change**; major = skill moves between bundles.
`plugin.json` and the marketplace entry must be bumped together
(`bundle_partition.bats` asserts they match).

**Domain bundles version in lockstep — a per-bundle matrix is unreleasable.**
`tools/build_manifest_release.py:188-192` (`_release_version`) raises
`ReleaseBuildError: domain bundle versions must match` unless all 8 domain
contracts carry an identical version. An earlier draft assigned patch to some
bundles and minor to others; that produces 0.2.1/0.3.0 skew and the release build
simply fails. Editing generated `plugin.json` files directly instead would trip
generated-view drift in `--check`.

**Rule:** each independently shipped stage picks **one** release version, set at
the highest level any touched bundle requires, and **any domain change bumps the
entire current domain set** — then regenerate the plugin and marketplace views.
Phrased as "the current domain set", not "all 8", because Phase 2b may take it to
13. Addons version independently, subject to the class decision in Phase 0 item 3.

**Hardcoded bundle inventories that must all be updated together.** `contracts.py`
is not the only one; a partial change fails `_release_version`, gets rejected by
parity verification, or silently stops triggering releases:

| Inventory | Consequence if missed |
|---|---|
| `src/manifest_agent/contracts.py:20` (`DOMAIN_BUNDLES`) | contract loading rejects the new bundle |
| `tools/check_plugin_runtime_paths.py:26` | runtime-path check skips or errors |
| `.github/workflows/plugin-parity-live.yml` (two tuples: ~:106 names, ~:159 name/category/description) | archive files outside the tuple are rejected |
| `.github/workflows/manifest-release.yml` (8 explicit path filters) | commits touching only a new bundle stop triggering releases |
| `tests/bats/{context_budget,constitution_check,code_quality_plugin_runtime}.bats` | fixed-count assertions fail |
| **`plugins/manifest-workspace/skills/deploy-reconcile/scripts/plugin_reconcile.py:11-20` (`EXPECTED_BUNDLES`)** | **false green** — a receipt containing only the old 8 still reports `status: converged`, hiding an incomplete upgrade and the moved commands |

`plugin_reconcile.py` is the worst of these because it is *shipped* as the
`/manifest-workspace:deploy-reconcile` runtime and its failure mode is silence,
not an error. Remove its independent bundle set and load it from the packaged
canonical catalog, and add a regression test proving that omitting any newly
added domain reports **drift**, not convergence. (This is exactly the defect class
`manifest-code-quality:false-green-check-audit` exists to catch.)

Add a CI assertion that every hardcoded inventory and workflow trigger matches the
canonical domain set, so this list cannot drift again.

| Stage | Domain lockstep version | Driven by | Addons |
|---|---|---|---|
| Phase 1 | `0.3.0` (minor) | **1.3b** retires two capabilities (`manifest-hooks.json` deleted) — see correction below | `manifest-delegate` → patch, bumped separately for `harness-routing.md` |
| Phase 2a | `0.4.0` (minor) | descriptions are always-on text; skills relocated behind shims | bump only if touched |
| Phase 2b | `1.0.0` (major) | skills move between bundles | per classification (§4 Phase 2b) |

Phase 1 is minor rather than patch because the lockstep takes the **highest**
level required by any bundle in the set, so all 8 go to `0.3.0`.

**Correction 2026-08-21 — the row's original two drivers were both wrong; the
level is right for a different reason.** It credited (a) "1.5 changes what
loads" and (b) "`issue-dev-auto` section deletion removes a capability".
Measured against `main` in the working tree: (a) **1.5 delivered nothing** — no
skill cleared its bar, zero flags were set (§4 1.5 OUTCOME); (b) there is no
`issue-dev-auto` section deletion — its `SKILL.md` was *modified* (+91/−30),
which is not a capability removal.

The minor level rests on **1.3b alone**: `manifest-workspace`'s
`hooks/manifest-hooks.json` is deleted outright and two advisory capabilities
are retired with a changelog tombstone — a genuine removal, and genuinely
minor-level. Every other Phase 1 repair that landed (1.3a vendoring, 1.3c
`_manifest` strip, 1.3d compose paths, 1.3e stitch tool-schema) is additive or
corrective, i.e. patch-level on its own. **One bundle carries the whole
lockstep.** If 1.3b were ever reverted or descoped, the other seven bundles
would have no minor-level justification left and this row must be re-derived,
not inherited.

**Acceptance:** upgrade from each currently published version, not a fresh
install, and confirm the fix is actually present in the installed cache.

**Exit gate — the bump is part of Phase 1, not a follow-up.** As of 2026-08-20 the
working tree carries capability-removing Phase 1.3 changes (the `manifest-hooks`
component removed, `_manifest` stripped, paths corrected, a `### Retired
capabilities` tombstone added to `CHANGELOG.md`) while
`plugins/manifest-workspace/manifest-capabilities.yml` is still `version: 0.2.0`.
Landing that as-is realises R8 exactly: `claude plugin update` no-ops on an
unchanged version, so neither the fix nor the tombstone reaches anyone.

**No Phase 1 change may merge until all 8 domain contracts are bumped to `0.3.0`
together.** Treat the bump as the final Phase 1 task with its own verification
(upgrade from the published version, confirm the change is present in the
installed cache), not as release paperwork that follows later.

*Note on scope:* an architecture-critic pass read this working-tree state as
already merged at `ad1faee3`. It is not — `git show ad1faee3:…/manifest-hooks.json`
still resolves, so the deletion and the CHANGELOG entry are both uncommitted. The
R8 exposure is therefore **prospective, not realised** — which is precisely why
this gate exists.

## 10. The 8 criticals (referenced by Phase 1 item 1.4)

1. `sub-agent-dispatch.md` phantom reference — **21 skills / 5 bundles**
   *(link checker)*. Corrected 2026-08-20: earlier drafts said 25/6 from a blunt
   string count; `manifest-spec-planning`'s 4 citations resolve correctly inside
   their own bundle and are not defects.
2. `issue-dev-auto` merge scripts — **CORRECTED 2026-08-20.** They are *not*
   missing: `pr_merge_loop.sh`, `merge_decision.sh` and `loop_lock.sh` exist at
   `configs/claude/scripts/` and are deployed to `~/.claude/scripts/`. The
   original audit's "not found anywhere" was a search-scope error (`find` run from
   inside `plugins/`). The real defect is the **same class as
   `command_config.yml`**: bootstrap-only, unreachable under a plugin-only
   install. *(link checker still catches it — the path is absent from the bundle)*
3. `manifest-workspace/hooks/manifest-hooks.json` schema — *not path-shaped*
4. `docker-compose-commandments` wrong script subpath *(link checker)*
5. stitch phantom `--api-key` flag — *not path-shaped*
6. `command_config.yml` bootstrap-only, 12 occurrences / 11 skills *(link checker)*
7. `token-benchmark` monorepo-only paths *(link checker)*
8. `a11y-audit` / `ux-review` unparseable cross-skill token
   `[[skill:manifest-workspace:parallel-agent]]` — ***not* caught by the link
   checker**; needs the token grammar gate (§4 1.4)
