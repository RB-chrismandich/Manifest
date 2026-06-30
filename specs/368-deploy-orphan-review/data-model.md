# Data Model: Deploy Reconciliation Review (368)

> Derived from `spec.md` (Key Entities, FRs, Edge Cases) and `research.md` (Topics 1–7 +
> Verification). All entities are **in-memory / ephemeral** — detection is stateless
> (FR-013, spec §"stateless"): each run rebuilds state from the current deployed tree and
> the current project source; nothing here is a persisted database. The only on-disk
> artifacts are the protection policy (`reconcile.yml`), the removal backup tree under
> `~/.manifest`, and the optional `--json` report. Field types use a language-neutral
> notation (`string`, `path`, `bool`, `enum`, `int`, `list<T>`, `map<K,V>`).

---

## 1. Managed Root

The set of deployment namespaces Manifest owns and writes into (FR-013). Orphan status is
only ever evaluated *inside* a managed root; anything outside is invisible to the review
(FR-009, Edge "Items the deploy does not manage").

| Field | Type | Notes |
|-------|------|-------|
| `tag` | enum{`claude`,`cursor`,`gemini`,`codex`,`antigravity`} | Stable home identifier; used in report grouping and backup sub-path (Topic 3 `<home-tag>`). |
| `path` | path | Absolute root, e.g. `~/.claude`. Base is `$HOME` unless overridden by `--home` / `MANIFEST_RECONCILE_HOME` (Topic 5, Verification #4). |
| `is_canonical` | bool | `true` only for `claude`; the secondaries mirror it via parent-dir symlinks (Topic 1). |
| `is_real_dir` | bool | `true` if the home holds a real directory rather than a symlink into `~/.claude` (Topic 4 risk: future per-home real dirs must still be enumerated). |

**Relationships.** A Managed Root *contains* zero-or-more Deployed Units. Secondary roots
*link into* the canonical root via Dependent Links.

**Validation rules.**
- Exactly the five tags above constitute scope (FR-013); no other path may be promoted to a
  Managed Root. (research Topic 1 §method (1).)
- The backup/trash root (`~/.manifest/...`) MUST NOT be a Managed Root — it is structurally
  outside scope so a later run never re-reports backed-up items (FR-010, Edge "Removal backup
  location"; Topic 3).
- `~/.claude/.agent_outputs` (a symlink into `~/.manifest`) is hard-excluded even though it
  sits under a managed root (Topic 1 §exclusions, Topic 4).
- A missing/empty root yields zero units, not an error (FR-012, Edge "Empty or missing
  deployed location").

**Lifecycle.** Static per run. Enumerated once at start from bootstrap constants + the
`--home` base.

---

## 2. Project Source Item

What the *current* project would deploy into a managed root — the source of truth that
defines "exists in our project" (spec Key Entities; FR-001).

| Field | Type | Notes |
|-------|------|-------|
| `unit_key` | string | Identity used for the present/absent comparison (skill top-level name, or config relative path). Must align with a Deployed Unit's `unit_key`. |
| `source_path` | path | Repo location: skills from `.skillshare/skills/`, configs from `configs/claude/` + `configs/<assistant>/` (Topic 5). |
| `target_root` | enum (Managed Root.tag) | Which home this item deploys into. |
| `would_deploy` | bool | Honors `services.yml` toggles, graphify gating, and merge-vs-full mode (Topic 5 risk: a toggled-off assistant must not be mis-reconciled). |

**Relationships.** A Project Source Item is the *counterpart* of a Deployed Unit by
`unit_key`; presence of a matching item means the unit is reconciled (not an orphan).

**Validation rules.**
- Resolution requires a project root: `--project` / `MANIFEST_REPO`, else auto-detect a git
  repo containing `configs/claude/`; **exit 2** if unresolvable (Topic 5 — the deployed
  `~/.claude/scripts` copy has no repo).
- "Would deploy" MUST reflect current toggles, not the static tree (FR-013 "what the current
  project would deploy"; Topic 5 risk).
- The comparison is current-vs-current only; deploy history is never consulted (spec
  §"stateless", FR-013; Edge "Disabled/toggled-off components").

**Lifecycle.** Built once per run from the project tree filtered by `services.yml`.

---

## 3. Deployed Unit

A unit physically present in a managed root, at **deployable-unit granularity** (FR-018,
spec Key Entities "Deployed item"). This is the atom of detection, classification, and
removal.

| Field | Type | Notes |
|-------|------|-------|
| `unit_key` | string | Relative-to-root POSIX identity (Topic 2 match semantics) — one key works across all five homes. |
| `unit_type` | enum{`skill`,`config`} | A `skill` = its whole top-level directory; a `config` = an individual file (FR-018). Wire field `unit_type` (contract §7). |
| `discovered_path` | path | Where it was found (may be under a secondary root). |
| `canonical_path` | path | `python3 os.path.realpath(discovered_path)` — NOT `readlink -f` (BSD/macOS lacks `-f`) (Topic 1). The dedup key. |
| `rel_path` | path | Path relative to its resolved managed root; the string matched against protection globs via `fnmatch.fnmatchcase` (Topic 2). |
| `root_tag` | enum (Managed Root.tag) | Home it was discovered under. |
| `is_symlink` | bool | `true` if `discovered_path` itself / its parent is a cross-home link (Topic 1 §method (2)). |

**Relationships.**
- *Resolved-into* an Orphan only if it has no matching Project Source Item.
- *Collapsed-by* `canonical_path`: many discovered units across homes → one logical unit
  (FR-017; Topic 1 §method (4): `realpath(~/.cursor/skills/foo) == ~/.claude/skills/foo`).
- *Pointed-at-by* zero-or-more Dependent Links.

**Validation rules.**
- Detection MUST NOT descend into a skill dir that still has a Project Source Item (FR-018,
  Edge granularity; avoids partially gutting a live skill).
- `skill` units come from `<root>/skills/*`; `config` units are individual files
  under `<root>/config` and per-home real artifacts (`~/.cursor/rules/*.mdc`, `mcp.json`;
  `~/.gemini/GEMINI.md`, `settings.json`; `~/.codex/AGENTS.md`) (Topic 1 §method (3)).
- Dangling/broken symlinks MUST be skipped or reported, never crash (`realpath` of a broken
  link returns a non-existent path) (Topic 1 risk, Topic 4 risk).
- Secondary-home symlinks are treated purely as Dependent Link *edges*, never as their own
  reconcilable units (Topic 4 §method (3)).

**Lifecycle.** Enumerated → canonicalized → deduped → (orphan check) → classified.

---

## 4. Orphan

A deduped Deployed Unit with **no corresponding Project Source Item** (spec Key Entities;
FR-001). One Orphan per `canonical_path` (FR-017).

| Field | Type | Notes |
|-------|------|-------|
| `canonical_path` | path | Primary identity (deduped) — removal always acts here, never through a secondary parent symlink (Topic 1). |
| `unit_key` | string | Carried from the Deployed Unit. |
| `unit_type` | enum{`skill`,`config`} | From the Deployed Unit. Wire field `unit_type`. |
| `root` | enum (Managed Root.tag) | Owning/canonical root tag (almost always `claude` for shared units). Wire field `root`. |
| `seen_in_roots` | list<enum> | *Internal only* — all home tags this canonical target was reachable from. NOT a wire field; the wire exposes `root` (owner) + `dependents` (active edges) instead. |
| `disposition` | Disposition | The KEEP/REMOVE verdict + reason (§5); flattened onto the wire item (no nested object). |

**Relationships.** Each Orphan *has exactly one* Disposition. Each Orphan *may have*
Dependent Links and *may match* Protection Policy Entries — both feed the Disposition.

**Validation rules.**
- Orphan-hood requires being inside a managed root with no current project source (FR-013);
  items outside managed roots are never Orphans (FR-009).
- A single shared target reachable from multiple roots is exactly one Orphan with one
  verdict — never double-reported or given conflicting verdicts (FR-017, Edge "Shared /
  symlinked deployed items").
- Toggled-off leftovers DO become Orphans (present-state judgement) — the desired drift
  surface (Edge "Disabled/toggled-off components").

**Lifecycle.** Transient: created during the scan, consumed by classification and (in
`--remove` mode) by the Removal Backup move; not persisted across runs (stateless).

---

## 5. Disposition

The classification applied to an Orphan, with a human-readable reason (spec Key Entities;
FR-002).

| Field | Type | Notes |
|-------|------|-------|
| `verdict` | enum{`KEEP`,`REMOVE`} | KEEP = protected/user-owned/shared-and-needed; REMOVE = eligible orphan (spec Key Entities). Wire field `verdict`. |
| `reason` | string | Human-readable justification (FR-002) — e.g. `protected: user-owned settings`, `shared target — active dependents: cursor`, `orphan: no project source`. Wire field `reason`. |
| `reason_code` | enum{`orphan_no_source`,`protected`,`shared_active_dependents`} | Machine-stable cause for `--json` and tests (contract §7; SC-003/SC-004 assertions). |
| `matched_pattern` | string? | The glob that triggered a `protected` KEEP; present on the wire only when `reason_code == protected` (contract §7). |
| `dependents` | list<enum>? | Secondary-home tags whose Dependent Links force a `shared_active_dependents` KEEP (FR-015). Wire field `dependents` (empty unless that reason_code). |

**Relationships.** One-to-one with Orphan. Derived from Protection Policy Entries (→ KEEP
`protected`) and Dependent Links (→ KEEP `shared_active_dependents`).

**Validation rules (classification precedence — fails toward KEEP).**
1. Hardcoded guards (trash dir, the `reconcile.yml` config files themselves) → KEEP
   (Topic 2 §precedence (1)).
2. Any Protection Policy match → KEEP `protected` (additive only; no negation, SC-004;
   FR-007/FR-014).
3. Any active Dependent Link resolving to/into the canonical path → KEEP
   `shared_active_dependents` (FR-008/FR-015).
4. Otherwise → REMOVE `orphan_no_source` (FR-014: an orphan matching no protection pattern
   with no active dependent is a REMOVE candidate).
- A REMOVE verdict is necessary-but-not-sufficient for deletion: the preview-first,
  explicit-opt-in flow (FR-003/FR-006/FR-010/FR-011) still gates the actual move.

**Lifecycle.** Computed once per Orphan; immutable for the run.

---

## 6. Protection Policy Entry

A path/name pattern that marks a matching Orphan KEEP — the concrete mechanism behind FR-007
(FR-014). Stored in the dedicated, committed `configs/claude/config/reconcile.yml`
auto-deployed to `~/.claude/config/reconcile.yml` (Topic 2; Verification #1 — NOT in
`command_config.yml` or `settings.local.json`).

| Field | Type | Notes |
|-------|------|-------|
| `glob` | string | A pattern under the `reconcile.protected:` key; matched case-sensitively via `fnmatch.fnmatchcase` against a unit's `rel_path`, with `*` spanning `/` (Topic 2 match semantics). |
| `source` | enum{`hardcoded`,`--protect`,`local`,`deployed`} | Provenance / precedence layer (Topic 2 §precedence (1)–(4)). |

**Relationships.** Many Protection Policy Entries → may match → many Orphans; a match sets
the Orphan's Disposition to KEEP `protected`.

**Validation rules.**
- The effective policy is the **union** of all four sources; protection is purely additive,
  any match → KEEP, no negation/unprotect (SC-004; Topic 2).
- Default set MUST cover everything `restore_runtime_state` preserves (high blast radius) —
  e.g. `settings.json`, `settings.local.json`, `.credentials.json`, `.agent_outputs`,
  `projects`, `plugins`, `commands`, `sessions`, `*.jsonl`, `.plans`, `.deployed-skills`,
  plus secondary-home `auth.json`, `oauth_creds.json`, `*.log` (Topic 2 defaults; FR-014).
- The policy MUST be overridable: repeatable `--protect GLOB`, machine-local
  `${MANIFEST_RECONCILE_CONFIG:-$MANIFEST_STATE_ROOT/reconcile.local.yml}` (outside managed
  scope, honors P-I), and the deployed/source `reconcile.yml` (FR-014; Topic 2).
- Config resolution: `RECONCILE_CONFIG` env, else `$SCRIPT_DIR/../config/reconcile.yml`
  (branch_clean idiom — repo when tested, `~/.claude/config` when deployed) (Topic 2).
- The trash dir and the config files themselves are protected as defense-in-depth in
  addition to being structurally out of scope (Topic 2/Topic 3).

**Lifecycle.** Loaded once per run from the union of sources; the deployed copy is
regenerated on every bootstrap redeploy (must stay byte-identical to source — parallel-agent
config-deploy gotcha; Topic 2 risk).

---

## 7. Dependent Link

A reverse-symlink edge proving a shared canonical target still has an active consumer — the
concrete mechanism behind FR-008 (FR-015/FR-016).

| Field | Type | Notes |
|-------|------|-------|
| `link_path` | path | The symlink location in a secondary home (e.g. `~/.cursor/skills`). |
| `target_path` | path | `realpath(link_path)` — the canonical `~/.claude/...` path it resolves to (Topic 4). |
| `source_root` | enum (Managed Root.tag) | Which secondary home owns the edge. |
| `is_active` | bool | `false` if the link is broken/dangling (target already gone) — must NOT force KEEP (Topic 4 risk). |

**Relationships.** A Dependent Link *points at* a canonical path; if that path is an Orphan,
the edge forces the Orphan's Disposition to KEEP `shared_active_dependents` naming
`source_root` in `dependents` (FR-015).

**Validation rules.**
- Edge index built by a **bounded** reverse scan: `find <home> -mindepth 1 -maxdepth 2 -type l`
  over only the four secondary homes (~20 edges) — NEVER a full-filesystem walk (FR-016;
  Topic 4; SC-006).
- An Orphan with one or more *active* edges resolving to/into its canonical path is KEEP; only
  targets with zero remaining active dependents are REMOVE-eligible (FR-015).
- Because secondaries link the whole top-level namespace dir, the shared-target KEEP bites at
  **namespace** granularity — removing a leaf skill/config under a still-linked parent never
  dangles a secondary link (Topic 1 §method (5), Topic 4 granularity nuance).
- `realpath` MUST be applied to both candidate and edge target before comparison; broken
  resolutions are non-dependents (Topic 4 risk).
- The trash root and foreign secondary entries are excluded from the edge scan (Topic 4).

**Lifecycle.** Rebuilt every run from present-state symlinks (stateless; no dependency DB).

---

## 8. Removal Backup

A timestamped trash tree where REMOVE orphans are moved instead of hard-deleted, enabling
restore (spec Key Entities; FR-010/SC-008). Only materialized in `--remove` mode.

| Field | Type | Notes |
|-------|------|-------|
| `run_ts` | string | `date +%Y%m%d_%H%M%S`; test-only override `MANIFEST_RECONCILE_TS`; same-second collision suffix guard (Topic 3; Verification #5). |
| `trash_root` | path | `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash/<run_ts>/` — uses `MANIFEST_STATE_ROOT` (exported), NOT `MANIFEST_STATE_DIR` (never exported → would expand empty) (Topic 3; Verification #2). Overridable via `--backup-dir` / `MANIFEST_RECONCILE_TRASH`. |
| `entries` | list<{src_canonical: path, dest: path, home_tag: enum}> | One row per moved orphan; dest = `<run_ts>/<home-tag>/<relative-path>/` so origins never collide (Topic 3). |
| `manifest_file` | path | `removed.tsv` written into the trash dir (Topic 3). |
| `restore_script` | path | Generated `restore.sh` in the trash dir; restores canonical first so secondary links re-resolve (Topic 3 risk). |
| `mode` | dir perms | Created `chmod 700` to match `~/.claude` (Topic 3). |

**Relationships.** A Removal Backup *contains* one entry per removed Orphan (those with
verdict REMOVE); reported back to the user as the restore location (FR-010 §"backup location
MUST be reported").

**Validation rules.**
- `trash_root` MUST validate as outside every managed root, else refuse (Topic 3; closes the
  "never re-report a backup" edge case, Edge "Removal backup location").
- Move uses `mv` (same-filesystem atomic) with an `rsync -a` + verified-`rm` EXDEV fallback;
  the copy MUST be verified before deleting the source or risk data loss (Topic 3 risk; SC-008).
- Only Orphans with verdict REMOVE are moved; KEEP items are never touched (SC-005/FR-010).
- Removal occurs against the **canonical** `~/.claude` path, never through a secondary parent
  symlink (Topic 1; leaf removal is dangle-safe).
- No auto-prune of old trash (retention note / future `--purge-trash`) (Topic 3 risk).

**Lifecycle / state.**
`absent` (preview/clean runs — SC-002 guarantees no backup dir is even created) →
`created` (first REMOVE move in a `--remove` run) →
`populated` (entries + `removed.tsv` + `restore.sh` written) →
`restorable` (durable until manually purged; SC-008 — 100% retrievable immediately after).
Preview is pure-read; once moved, the next stateless scan no longer sees the item (Topic 3
idempotency).

---

## 9. Reconciliation Report

The output of a review run: the deduped per-orphan list with dispositions + summary counts
(spec Key Entities; FR-003/FR-004). Human-readable by default; machine-readable with `--json`.

> **Single source of truth for the wire format:** the `--json` object schema and the
> human-readable stdout format are defined canonically in
> [`contracts/reconcile-cli.md`](./contracts/reconcile-cli.md) §7 (JSON) and §5–6 (stdout).
> This section maps the internal entities to that contract; on any discrepancy, the contract
> wins. The field names below MUST match the contract exactly so tests/smoke captures encode
> one stable shape.

| Field | Type | Notes |
|-------|------|-------|
| `mode` | enum{`preview`,`remove`} | Read-only run vs a completed `--remove` run (contract §7). |
| `project` | path | Resolved project root. |
| `roots` | list<string> | Managed roots reviewed (1 if `--root` given). |
| `summary.orphans` | int | Total orphans; `orphans == keep + remove` (FR-004). |
| `summary.keep` | int | Count classified KEEP. |
| `summary.remove` | int | Count classified REMOVE. |
| `items` | list<object> | One per deduped Orphan (FR-017); fields flattened per contract (no nested `disposition`). |
| `removed` | null \| list<{`canonical_path`,`backup_path`}> | `--remove` only; `null` in preview (FR-010). |
| `backup_dir` | null \| path | `--remove` only; the timestamped trash dir; `null` in preview. |

Each `items[]` entry is the wire projection of one Orphan + its Disposition:
`canonical_path`, `display_path` (tilde-abbreviated), `root` (owning root tag),
`unit_type` (`skill`\|`config`), `verdict` (`KEEP`\|`REMOVE`), `reason_code`
(`orphan_no_source`\|`protected`\|`shared_active_dependents`), `reason` (human string),
`matched_pattern` (present only when `reason_code == protected`), and `dependents`
(secondary-home tags with an active edge; empty unless `shared_active_dependents`). The clean
state (FR-012/SC-001) is `summary.orphans == 0` with an empty `items` array.

See [`contracts/reconcile-cli.md`](./contracts/reconcile-cli.md) §7 for the full annotated
example and field-by-field contract table; that example is authoritative.

**Relationships.** Aggregates all Orphans + (optionally) one Removal Backup. The deploy-time
`reconcile_deploy_report()` consumes the summary only (preview mode), prints KEEP/REMOVE
counts, and is fail-open (FR-005/FR-006; Topic 5).

**Validation rules.**
- Preview runs are byte-for-byte non-mutating (SC-002); the deploy-time call is preview-only,
  never `--remove`, and swallows errors so it can never fail a deploy (FR-006; Topic 5
  §exit-codes — orphans-found NEVER yields nonzero).
- A fully-matching environment emits an explicit clean result, not an error (FR-012/SC-001).
- Exit codes: `0` = success (preview/clean/removal-done), `1` = removal-action failure,
  `2` = usage / cannot-resolve-project (Topic 5).

**Lifecycle.** Produced at the end of each run; not persisted except as the optional `--json`
stream the caller redirects.
