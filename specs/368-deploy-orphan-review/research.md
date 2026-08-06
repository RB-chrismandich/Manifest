# Phase 0 Research: Deploy Reconciliation Review (368)

> Feature: compare what Manifest has **deployed** into the assistant homes
> (`~/.claude` + mirrored `~/.cursor ~/.gemini ~/.codex ~/.antigravity`) against what the
> **project** would currently deploy, report orphans classified KEEP/REMOVE, preview by
> default, recoverable opt-in removal. Spec: `specs/368-deploy-orphan-review/spec.md`.

## Resolved unknowns

- **Symlink resolution + cross-home dedup** → canonicalize each unit with `python3 os.path.realpath`, key the report by canonical path, one verdict per shared target (Topic 1).
- **Protection policy storage + override** → new `configs/claude/config/reconcile.yml` (auto-deployed), env override `RECONCILE_CONFIG`, machine-local `~/.manifest/reconcile.local.yml`, repeatable `--protect` (Topic 2).
- **Recoverable removal backup** → timestamped trash under `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash/<ts>/`, with `removed.tsv` + generated `restore.sh` (Topic 3).
- **Bounded active-dependent detection** → reverse-symlink scan of only the 4 secondary homes (`find -type l`, ~20 edges), never a filesystem walk (Topic 4).
- **Entry points / deploy-time integration** → new skill `/deploy-reconcile` wrapping `configs/claude/scripts/deploy_reconcile.sh`; fail-open report-only call in `bootstrap.sh main()` after `deploy_configs` (Topic 5).
- **Test + smoke plan** → bats `tests/bats/deploy_reconcile.bats` + first `smoke-catalog/manifest.yaml` (tier Lite, cli) for the P-VI Verify gate (Topic 6).
- **Reuse-vs-new + final name** → NEW skill `deploy-reconcile`, modeled on `branch-clean`; do not extend sync-configs / health-check / deploy-drift-root-cause / parallel_agent.py (Topic 7).
- **Canonical CLI contract** (cross-topic, post-verification): `deploy_reconcile.sh [--remove] [--yes] [--json] [--project DIR] [--home DIR] [--root DIR] [--config PATH] [--backup-dir DIR] [--help]`; default preview; env `RECONCILE_CONFIG`, `MANIFEST_RECONCILE_HOME`, `MANIFEST_RECONCILE_TRASH`, `MANIFEST_RECONCILE_TS` (test-only).

---

## Topic 1 — Symlink resolution + cross-home dedup

**Decision.** Canonicalize every candidate deployable unit with `python3 os.path.realpath` (NOT shell `readlink -f`, absent on BSD/macOS), dedup on the resolved absolute path, key the reconciliation report by canonical path so each shared target gets exactly one KEEP/REMOVE verdict, and always perform removal against the canonical (`~/.claude`) path — never through a secondary-home parent symlink.

Method: (1) managed roots = canonical `~/.claude` plus secondaries `~/.cursor ~/.gemini ~/.codex ~/.antigravity`; backup trash lives under `~/.manifest`, outside every root. (2) For each secondary home, record symlink edges (`os.path.islink` → `realpath`) — in the live tree these are the **parent-directory** links `scripts/ config/ prompts/ .plans/ skills/ -> ~/.claude/<name>` from `link_shared_assets`. (3) Enumerate units per root: skills = top-level dirs under `<root>/skills`, config = individual files under `<root>/config`, plus per-home real artifacts (`~/.cursor/rules/*.mdc`, `mcp.json`; `~/.gemini/GEMINI.md`, `settings.json`; `~/.codex/AGENTS.md`). (4) Collapse units by canonical path: because the links are parent-level, `realpath(~/.cursor/skills/foo) == ~/.claude/skills/foo`, so all four secondary copies collapse onto the single `~/.claude` entry. Secondary-only real units (`rules/`, `GEMINI.md`, `mcp.json`, foreign dirs) resolve to themselves → distinct keys. (5) Remove only the canonical path; leaf removal is dangle-safe because consumers link the surviving **parent** dir. Before removing canonical `P`, assert no edge target equals `P` exactly (else KEEP "shared target with active dependents"). Hard-exclude shared parent dirs, the dir-level shared symlinks, and `~/.claude/.agent_outputs` (symlink into `~/.manifest`, leaves managed scope).

**Rationale.** The deployment shares content via **directory-level** symlinks, not per-file links. realpath-keyed dedup is therefore free and correct (FR-017), and leaf removal can never orphan a link because the link points at a surviving parent (FR-008). `python3` is the portable realpath (macOS ships BSD `readlink` without `-f`); the repo already depends on python3. Backups under `~/.manifest` are provably outside scope, closing the "never re-report a backup" edge case.

**Alternatives considered.** `readlink -f` — rejected (BSD/macOS lacks `-f`). Inode (st_ino/st_dev) dedup — rejected (loses human-readable canonical path needed for report/backup; dangle check is about link *targets*, not inodes). Per-home independent reconcile then merge — rejected (risks conflicting verdicts, FR-017). Per-leaf dangling checks for every shared link — rejected as over-engineering (links are parent-level). Keep secondary copies as separate "shared"-tagged entries — rejected (FR-017 mandates reported once).

**Evidence.**
- `bootstrap.sh:58-71` — TARGET_DIR=`~/.claude`; CURSOR/GEMINI/CODEX/ANTIGRAVITY_TARGET_DIR; `MANIFEST_STATE_DIR="$HOME/.manifest"`.
- `bootstrap/lib/common.sh:83-105` — `link_shared_assets` links `scripts/config/prompts/.plans` (+`skills` when 3rd arg `true`) at **parent-directory** level (verified: `symlinks=(scripts:$TARGET_DIR/scripts …)`).
- `bootstrap/lib/common.sh:57-79` — `create_symlink`: `ln -sf`; backs up real (non-link) paths instead of `rm -rf`.
- `bootstrap/lib/deploy.sh:243,321,350,367` — each secondary home calls `link_shared_assets … 'true'`.
- `bootstrap/lib/common.sh:171-172` — comment: assistant skill dirs symlink to home, so gating the home copy clears all targets (confirms parent-level propagation).
- `bootstrap/lib/deploy.sh:163` — `.agent_outputs` created as symlink into `MANIFEST_OUTPUT_DIR` (must be excluded).

**Risks.** A future switch from parent-dir to per-unit symlinks would make leaf removal able to dangle a link — guarded by the edge-equality check, which must stay in sync. Foreign/real dirs Manifest never deploys (e.g. an out-of-namespace `skills-*` dir) survive realpath dedup as distinct keys and would be mis-flagged REMOVE unless the project deploy-map scopes which namespaces Manifest owns per home (FR-009/FR-014). `realpath` of a broken symlink returns a non-existent path — enumeration must skip/report dangling links, not crash. Symlink cycles yield an unresolved path (low risk). A user who manually replaced a shared dir with a real copy produces divergent real units (each reconciled in place) — document so it is not mistaken for a dedup bug. *The specific live realpath equalities and any foreign-dir names are re-asserted by the bats fixture, not assumed (see Verification).*

---

## Topic 2 — Protection policy (FR-007 / FR-014)

**Decision.** Back the protection policy with a NEW dedicated, committed file `configs/claude/config/reconcile.yml`, auto-deployed to `~/.claude/config/reconcile.yml` because `deploy_configs` rsyncs all of `config/`. Do NOT store the policy in `settings.local.json` (user-owned, already shipped) or in `command_config.yml`. **(Amended per Verification: the top-level `deploy_reconcile:` data block previously proposed inside `command_config.yml` is dropped; only the `tool_policies` registration entry remains there.)**

Schema = flat glob list under a `reconcile.protected:` key, mirroring `branch_clean.protected`. Defaults cover the runtime/user-owned set grounded in a live `~/.claude`: `settings.json`, `settings.local.json`, `.credentials.json`, `.agent_outputs`, `projects`, `plugins`, `commands`, `ide`, `sessions`, `tasks`, `todos`, `shell-snapshots`, `statsig`, `cache`, `backups`, `security`, `history.jsonl`, `*.jsonl`, `.last-*`, `.plans`, `plans`, `.deployed-skills`; secondary-home auth/state `auth.json`, `oauth_creds.json`, `*.log`.

Match semantics: each candidate is identified by its POSIX path **relative to its resolved managed root** (one pattern works across all 5 homes), matched case-sensitively via `fnmatch.fnmatchcase` (equiv. bash `[[ "$rel" == $glob ]]`) where `*` spans `/`. Protection is purely **additive** (any match → KEEP; no negation, per SC-004). Precedence is a union that only grows: (1) hardcoded guards (the trash dir + the reconcile config files themselves), (2) repeatable `--protect GLOB`, (3) machine-local `${MANIFEST_RECONCILE_CONFIG:-$MANIFEST_STATE_ROOT/reconcile.local.yml}` outside managed scope, (4) deployed/source `reconcile.yml`. Config resolution: `CONFIG="${RECONCILE_CONFIG:-$SCRIPT_DIR/../config/reconcile.yml}"` (branch_clean idiom — resolves to `~/.claude/config` when deployed, repo when tested).

**Rationale.** The protection boundary already exists implicitly: `restore_runtime_state` excludes the repo-owned top-level entries and restores everything else as "user/runtime state" — exactly the orphan-vs-protected line. A dedicated `reconcile.yml` matches the `skillclaw.yml`/`linear_triage.yml`/`parallel_agent.yml` scope-isolation precedent, auto-deploys via the existing rsync, and is itself a project source so it can never be flagged as its own orphan. Additive-only union fails toward KEEP. The `~/.manifest` override lets users add protections without editing the redeploy-overwritten tree (honors P-I).

**Alternatives considered.** Key in `command_config.yml` (the literal branch_clean precedent) — rejected (file already ~29 KB; dedicated file matches skillclaw scope-isolation). Overrides in `settings.local.json` — rejected (user-owned, P-I anti-pattern). Derive protected set at runtime from `restore_runtime_state` — rejected (FR-014 wants a documented, auditable, overridable list). Per-root nested schema — deferred (flat union is simpler and over-protection is the safe direction). Negation/unprotect patterns — rejected (violates SC-004; the preview + opt-in flow is the escape hatch). Backup inside `~/.claude` relying on a glob — rejected (out-of-scope `~/.manifest` makes exclusion structural).

**Evidence.**
- `bootstrap/lib/deploy.sh:9-37` — `restore_runtime_state`: repo owns only `configs/claude` contents; everything else under `~/.claude` is user/runtime state (the protection boundary); `.agent_outputs` special-cased.
- `bootstrap/lib/deploy.sh:144` — `deploy_configs` rsyncs all of `config/`, so a new `reconcile.yml` auto-deploys.
- `bootstrap/lib/common.sh:142` — `.deployed-skills` is Manifest's own prune manifest (metadata, not a skill).
- `configs/claude/scripts/branch_clean.sh:29` — `CONFIG="${BRANCH_CLEAN_CONFIG:-${SCRIPT_DIR}/../config/command_config.yml}"` env+SCRIPT_DIR idiom (verified).
- `configs/claude/scripts/branch_clean.sh:62` — repeatable `--protect GLOB` (verified).
- `configs/claude/config/command_config.yml:758-764` — `branch_clean.protected` flat glob list (schema shape to reuse).
- `configs/claude/config/skillclaw.yml` — precedent for a dedicated feature-scoped config file.

**Risks.** Granularity for `.plans/` and `config/`: FR-018 says config reconciled per-file, but those dirs mix repo-shipped (sourced) and runtime files; protecting whole `.plans` is safe, but a user-dropped `config/foo.yml` would be flagged — document per-file `config/` reconciliation and add targeted protections. Flat globs over-protect across roots (safe direction, lower REMOVE recall). `*` crossing `/` is non-obvious — the `reconcile.yml` header must document it. Deployed vs source copy must stay identical (parallel-agent config deploy gotcha) — smoke test should assert. `~/.manifest/reconcile.local.yml` is invisible until a user knows to create it — document (optionally seed a commented template). Secondary-home auth filenames drift with CLI versions — additive union + preview mitigate; periodic review needed.

---

## Topic 3 — Recoverable removal backup (FR-010 / SC-008)

**Decision.** Move REMOVE orphans into a timestamped trash tree under `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash/<RUN_TS>/` — outside managed scope, never hard-delete by default; report the path; restore via a generated `restore.sh` + `removed.tsv` manifest written into the backup dir; gate destructive mode behind `--remove` + (interactive `/dev/tty` confirm OR `--yes` OR `RECONCILE_ASSUME_YES=1`). **(Amended per Verification: the trash root uses `MANIFEST_STATE_ROOT`, the exported/profile var — NOT `MANIFEST_STATE_DIR`, which is never exported and would expand empty in the child process.)**

Details: `<RUN_TS>=$(date +%Y%m%d_%H%M%S)` computed at runtime (the deploy.sh:88 / common.sh:71 idiom); test-only override `MANIFEST_RECONCILE_TS`; same-second collision suffix guard. Structure: `<RUN_TS>/<home-tag>/<relative-path>/` so orphans never collide and the origin is self-evident. Trash root override `--backup-dir` / env `MANIFEST_RECONCILE_TRASH`, validated to be outside every managed root (else refuse). Use `mv` for same-filesystem atomicity with an `rsync -a` + verified-`rm` EXDEV fallback (rsync `-a` preserves symlinks, as `restore_runtime_state`). Self-exclusion is structural (trash outside roots) + a default protection pattern as defense-in-depth. Idempotency: preview is pure-read; once moved, the next stateless scan no longer sees the item. Create the trash dir `chmod 700` (matches `~/.claude` perms).

**Rationale.** `~/.manifest` is the one Manifest-owned location deliberately kept outside `~/.claude` (deploy.sh comment: `.agent_outputs … outside ~/.claude and therefore never part of the backup`), making it the natural orphan-safe trash. The repo already has a recoverable move-aside pattern (`.backup.<ts>`) and a manifest-driven scoped-prune pattern (`.deployed-skills`); reusing both keeps reviewers on familiar ground. The destructive-mode gating copies `branch_clean.sh` (`--apply`/`--yes` + `/dev/tty`), giving a proven non-interactive path.

**Alternatives considered.** Trash inside `~/.claude` — rejected (re-flagged by later reviews; fragile name-based self-exclusion). Hard delete — rejected by FR-010/SC-008. OS trash (`~/.Trash`/XDG/gio) — rejected (non-portable, external dep, splits recovery state). Deploy-history DB — rejected (locked stateless). Single shared trash dir — rejected (concurrent/repeat runs collide). git stash/commit — rejected (overkill; homes aren't a git repo).

**Evidence.**
- `bootstrap.sh:67,69,71` — `MANIFEST_STATE_DIR="$HOME/.manifest"` (plain assignment, **not exported**); `MANIFEST_OUTPUT_DIR`/`MANIFEST_TMP_DIR` nested under it.
- `bootstrap/lib/auth.sh:241` — `export MANIFEST_STATE_ROOT="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"` written to profile (the env idiom to reuse).
- `bootstrap/lib/deploy.sh:28-33` — comment: `~/.manifest` is outside `~/.claude` and never part of the backup.
- `bootstrap/lib/deploy.sh:88` — `backup_dir="$TARGET_DIR.backup.$(date +%Y%m%d_%H%M%S)"` (timestamp + move-aside precedent).
- `bootstrap/lib/common.sh:69-78` — `create_symlink` backs up to `${link_path}.backup.$(date …)` instead of `rm -rf`.
- `bootstrap/lib/common.sh:137-164` — `.deployed-skills` manifest drives a bounded scoped prune with traversal-safety guards.
- `bootstrap/lib/deploy.sh:37` — `rsync -a` preserving symlinks/attrs (cross-device fallback pattern).
- `configs/claude/scripts/branch_clean.sh:13,18` (`--apply`/`--yes`), `:182-192` (dry-run default + `/dev/tty` confirm) — destructive-mode contract.
- `bootstrap/lib/deploy.sh:130` — `~/.claude` is `chmod 700` (trash should match).

**Risks.** EXDEV cross-device move must verify copy succeeded before deleting source (else data loss). Shared symlinked targets: removal operates on canonical `~/.claude`; `restore.sh` must restore canonical first so secondary links re-resolve. Trash growth — no auto-prune (like unbounded `~/.skillclaw/sessions`); flag a retention note / `--purge-trash` for the plan. `MANIFEST_RECONCILE_TS` must stay test-only + keep the same-second suffix guard.

---

## Topic 4 — Bounded active-dependent detection (FR-015 / FR-016)

**Decision.** Detect active dependents by a bounded reverse-symlink scan of only the four secondary homes, never a filesystem walk. Per run: (1) define roots from bootstrap constants; (2) build the dependent-edge index with `find <home> -mindepth 1 -maxdepth 2 -type l`, recording `(L -> realpath(L))` (~5 links × 4 homes ≈ 20 edges; `link_shared_assets` only creates depth-1 links, maxdepth 2 is cheap insurance); (3) treat each secondary symlink purely as an edge, never its own reconcilable unit; (4) a canonical target `T` under `~/.claude` has an active dependent iff some edge's resolved target `== T` or is a descendant under `T` → KEEP naming the dependent home(s), else REMOVE-eligible.

REMOVE-eligibility = orphan (no project source) AND matches no protection pattern AND no active dependent edge resolves to/into it. Granularity nuance: secondaries link the whole top-level namespace dir, so removing a leaf skill/config never dangles a secondary link; the shared-target KEEP rule bites only at **namespace** granularity (and protects `~/.claude/.agent_outputs`). Portability: `realpath` with a `python3 os.path.realpath` / `cd <dir> && pwd -P` fallback (BSD `readlink -f` unsupported). Exclude the trash root and foreign secondary entries from both unit enumeration and the edge scan.

**Rationale.** `link_shared_assets` is the ONLY producer of cross-home links and emits ≤5 fixed top-level symlinks per home, so the dependent universe is tiny and known a priori — the scan is by construction not a full-filesystem traversal (FR-016) yet covers exactly the consumers Manifest creates (FR-008/FR-015). ~20 realpath calls are negligible next to the deploy's full-tree rsync and `find -type f` over all of `~/.claude` (SC-006). Resolving + deduping by realpath satisfies FR-017 in the same pass.

**Alternatives considered.** Full-filesystem `find / -type l` — rejected (violates FR-016, blows SC-006). Dependency DB — rejected (locked stateless; reverse scan reconstructs edges from present state). Per-home unit reconcile — rejected (double-reports, FR-017). `readlink -f` — rejected (BSD unsupported). Per-skill dependent lookup as the primary mechanism — rejected (secondaries link the parent dir, no per-skill edge exists; the descendant-path check still handles any future per-unit link).

**Evidence.**
- `bootstrap/lib/common.sh:88-96` — fixed symlink set `scripts/config/prompts/.plans` (+`skills`) → `$TARGET_DIR/<name>`: the complete dependent-edge universe.
- `bootstrap/lib/common.sh:57-79` — `create_symlink` does `ln -sf`, so every secondary managed entry is a symlink into `~/.claude`.
- `bootstrap.sh:58-66` — the 5 managed roots (scope bounds).
- `bootstrap/lib/deploy.sh:163` — `.agent_outputs` symlink into `~/.manifest`, protected by the namespace-level KEEP rule.
- `bootstrap/lib/deploy.sh:199-206` — `list_deployed_files` runs `find -type f` over the whole target every deploy (the cost baseline ~20 realpaths is dwarfed by).
- `bootstrap/lib/deploy.sh:144` — full-tree `rsync -a` per deploy (dominant cost).

**Risks.** A secondary home that ever holds a REAL managed-namespace dir instead of a symlink (gate_graphify_skill already anticipates this) would make the edges-only model under-count — the unit walk must also reconcile a secondary home's namespace if it is a real dir. Broken/dangling secondary symlinks are NOT active dependents (target already gone) and must not force KEEP — treat non-existent resolutions as non-dependents (optionally report as stale). realpath must be applied to BOTH the candidate and the edge target before comparison. maxdepth must stay capped (never unbounded). Exclude the trash root from the scan.

---

## Topic 5 — Integration + entry points

**Decision.** SCRIPT `configs/claude/scripts/deploy_reconcile.sh` (Bash, `set -euo pipefail`, bash 3.2-safe). CLI:
`deploy_reconcile.sh [--remove] [--yes] [--json] [--project DIR] [--home DIR] [--root DIR] [--config PATH] [--backup-dir DIR] [--help]`. Default = read-only preview.
- `--project DIR` — repo source root for "what the project would deploy" (skills from `.retired skill supply/skills`, configs from `configs/claude` + `configs/<assistant>`). Default: env `MANIFEST_REPO`, else auto-detect a git repo containing `configs/claude/` from the script's location; **exit 2** if neither resolves (the deployed `~/.claude/scripts` copy has no repo).
- `--home DIR` / env `MANIFEST_RECONCILE_HOME` — **override the base for all five managed roots** (testability hook; default `$HOME`). **(Added per Verification — required for hermetic bats + the P-VI smoke gate.)**
- `--remove` — destructive: move REMOVE orphans to the recoverable backup; requires confirm unless `--yes`.
- `--yes` / `RECONCILE_ASSUME_YES=1` — documented non-interactive path (FR-010).
- `--json` (FR-004); `--root DIR` scopes to one root; `--config PATH` / env `RECONCILE_CONFIG` (default `$SCRIPT_DIR/../config/reconcile.yml`); `--backup-dir DIR` / env `MANIFEST_RECONCILE_TRASH`.
- `err() { echo "deploy-reconcile: $*" >&2; }`; `--help` ≤15 lines, exit 0.
- Exit codes: 0 = success (preview/clean/removal-done) — **orphans-found NEVER yields nonzero** so the deploy-time report cannot fail the deploy; 1 = removal-action failure; 2 = usage / cannot-resolve-project.

SKILL `.retired skill supply/skills/deploy-reconcile/SKILL.md`, `/deploy-reconcile`, body modeled on `branch-clean` (Preview → Apply-with-confirm → Review-outcome → Safety). Register in `command_config.yml` `tool_policies` (allowed Bash; parallel_agents conditional — Tier 1 on the `--remove` path; subagents never). Hyphen-skill/underscore-script symmetry (branch-clean ↔ branch_clean.sh).

DEPLOY-TIME: add fail-open `reconcile_deploy_report()` in `bootstrap/lib/deploy.sh`, invoked from `bootstrap.sh main()` immediately after `deploy_configs` + its `after_deploy` hook, guarded: `reconcile_deploy_report || print_warning "reconcile review skipped (non-fatal)"`. Runs `deploy_reconcile.sh --project "$SCRIPT_DIR"` **preview only** (never `--remove` — FR-006), prints the KEEP/REMOVE summary (FR-005), swallows errors (P-V). Placed in `main()` (not inside `deploy_configs`, which has a merge-mode early return at deploy.sh:117 and full-mode end at deploy.sh:192) so a single call covers both deploy paths against settled state. Runs BEFORE `verify_installation` and MUST NOT contribute to `verify_errors` (only that drives `exit 1` — P-V keeps the report advisory while bootstrap still exits non-zero on real verify failures).

**Rationale.** P-IV is satisfied by a skill wrapping a dedicated script (branch-clean precedent), no logic on parallel_agent.py. The dual-mode + `--yes`/`--json`/`err()`/≤15-line-help shape is proven in `branch_clean.sh`/`label_sync.sh`. P-V fail-open is met by the `|| …` guard under `set -e`. Report-only (FR-006) is structural: no `--remove` + exit 0 on orphans. Backup under `~/.manifest` reuses the out-of-scope state root.

**Alternatives considered.** Wire via `after_deploy`/`after_verify` module hook — rejected (optional extension registry, FR-005 needs the review to ALWAYS run). Call at end of `deploy_configs()` — rejected (misses the merge-mode early return). Reuse `.deployed-skills` as the project source — rejected (deploy-time artifact; spec mandates stateless current-project read via `--project`). Names `deploy-orphans`/`orphan-review`/`reconcile-deploy` — rejected for `deploy-reconcile` (clearest invocation + branch-clean symmetry). Nonzero exit on orphans (CI gate) — rejected (pre-merge gate is out of scope; breaks fail-open).

**Evidence.**
- `bootstrap.sh:38` — `set -e` (deploy-time call must be guarded).
- `bootstrap.sh:58-71` — 5 managed roots + `MANIFEST_STATE_DIR`/`MANIFEST_OUTPUT_DIR`.
- `bootstrap.sh:260-262` — `deploy_configs` + `after_deploy` hook + skillclaw apply (insertion point).
- `bootstrap.sh:328-341` — `verify_installation` guarded into `verify_errors`; only `verify_errors>0` → exit 1.
- `bootstrap/lib/deploy.sh:42,117,192` — `deploy_configs` with merge-mode early return (117) and full-mode end (192).
- `bootstrap/lib/deploy.sh:101,144` — rsync merge (`--ignore-existing --exclude '/skills'`) and full (`-a --exclude '/skills'`) modes — config files are the per-file deployable units.
- `configs/claude/scripts/branch_clean.sh:21,38,42-69,182-192` — exit-code/err()/usage/dry-run-default/`--apply`/`--yes`/JSON pattern (verified).
- `configs/claude/scripts/label_sync.sh:16-18` — `err()` convention.
- `configs/claude/config/command_config.yml:758-764` — branch_clean policy block; tool_policies registration shape.

**Risks.** Project-source resolution from the deployed copy: on-demand runs must supply `--project`/`MANIFEST_REPO` (exit 2 + SKILL.md guidance). "What the project would deploy" must honor `services.yml` toggles + graphify gating + merge-vs-full mode, or a disabled assistant home is mis-reconciled — the script must read `services.yml`, not just the static tree. realpath dedup must handle both shared-symlink and (future) independent-copy cases. Protection defaults must cover everything `restore_runtime_state` preserves (high blast radius) — gated by the live-fixture test.

---

## Topic 6 — Test + smoke plan

**Decision.** Cover the script with a new bats suite `tests/bats/deploy_reconcile.bats` driven by a fake managed-home fixture, keep classification in Bash (bats primary; pytest only if a Python YAML-policy/dedup helper is factored out), and satisfy the P-VI Verify gate by shipping the repo's FIRST smoke catalog `smoke-catalog/manifest.yaml` — app `manifest`, tier `Lite`, type `cli` — that runs the deployed `deploy_reconcile.sh` in dry-run against a hermetic temp fixture and asserts exit 0, gated via `smoke_test.py run --app manifest --tier Lite --junit smoke-lite.xml`. **(Amended per Verification: filename is `deploy_reconcile.bats`/`deploy_reconcile.sh` everywhere — NOT `reconcile_deploy.*`; hermeticity uses the `--home`/`MANIFEST_RECONCILE_HOME` all-roots override added to Topic 5.)**

Required testability hooks (design-to): `--home`/`MANIFEST_RECONCILE_HOME` (all five roots → SANDBOX), `--project`, `--backup-dir`/`MANIFEST_RECONCILE_TRASH`, `MANIFEST_RECONCILE_TS` (test-only). Default preview; `--remove`+confirm with `--yes` non-interactive; `--json`; `--help` ≤15 lines exit 0; `err()`.

Bats cases (fixture = mktemp SANDBOX with fake `$HOME/.claude{,/skills,/config}` + `.cursor/.gemini/.codex/.antigravity` skills symlinked into `.claude`, plus a fake project): 1 `--help` exits 0, ≤15 lines, before any dependency/home lookup; 2 dry-run non-mutation (SC-002) via before/after `find|sort`+checksums; 3 project-present item not listed (FR-001); 4 REMOVE classification + counts (FR-002/SC-003/FR-004); 5 KEEP via protection policy + user override (FR-007/FR-014/SC-004); 6 dedup across homes — one symlinked orphan reported once (FR-017); 7 shared-target active-dependent KEEP (FR-008/FR-015); 8 deployable-unit granularity — never descend into a still-present skill (FR-018); 9 managed-scope boundary — out-of-root file never reported (FR-009/FR-013); 10 backup+restore on `--remove` under `~/.manifest`, recoverable (FR-010/SC-005/SC-008); 11 backup excluded from scope — second run never re-reports (edge case); 12 opt-in gating — `--remove` without confirm/`--yes` removes nothing (FR-011); 13 missing `~/.claude` → zero orphans, exit 0 (edge); 14 clean state → "no orphans" (FR-012); 15 deploy-time fail-open — forced reconcile error WARNs, deploy succeeds, nothing deleted, normal report prints summary but never creates a backup dir (US2/P-V/FR-005/FR-006).

**(Amended 2026-06-30, implementation): engine language = `python3` core + bash CLI wrapper.**
macOS bash 3.2 lacks associative arrays, and the engine is data-heavy (enumerate units across 5
homes, realpath-dedup, fnmatch classify, emit JSON). So the read-only classification core lives in
`configs/claude/scripts/reconcile_core.py` (pure-read: enumerate → dedup → classify → render
human/JSON), and `configs/claude/scripts/deploy_reconcile.sh` is the bash CLI wrapper (args, `--help`,
confirm gate, and the destructive move/backup/restore). This makes `pytest`
(`tests/python/test_reconcile_policy.py`) the primary harness for the pure classification functions and
keeps `bats` for the CLI/integration/destructive path. (Supersedes the "classification in Bash" note
below; the bats plan and all flags/contracts are unchanged.)

Pytest covers the factored Python helper (`tests/python/test_reconcile_policy.py`: pattern-match, dedup-by-realpath, active-dependent as pure functions). Smoke shape (tier Lite, no Playwright): build a throwaway fixture home+project, run `deploy_reconcile.sh --home <fixture> --project <fixture> --json` with `expect_exit: 0` + a `captures` regex on the summary line. EMPTY selection (exit 2) is a failure not a pass, so the catalog MUST contain ≥1 Lite test.

**Rationale.** The repo is bats-first for bootstrap/deploy shell logic (`deploy_skills.bats` sources `common.sh` and exercises `deploy_home_skills`/`gate_graphify_skill` against a mktemp SANDBOX with env-overridden TARGET_DIR/CURSOR_TARGET_DIR) — the reconcile script fits that mold. The smoke system (`smoke_test.py` → `smoke_orchestrator`) is the P-VI Verify gate, supports a browser-free cli tier-Lite test, and defaults its catalog dir to `smoke-catalog/`. Keeping classification in Bash (with optional inline python3 for YAML) keeps bats primary.

**Alternatives considered.** Bolt reconciliation into `deploy_home_skills`' `.deployed-skills` prune — rejected (violates P-IV/P-VI; skills-only, no configs/all-homes/KEEP-REMOVE/backup). Python module + pytest primary — rejected (duplicates fixture cost; diverges from `deploy_skills.bats`). Deploy-time bats e2e as the critical-path coverage — rejected (P-VI specifically requires the smoke orchestrator exit 0). ui/agent smoke step — rejected (cli is hermetic, browser-free, fast).

**Evidence.**
- `bootstrap/lib/deploy.sh:42` — `deploy_configs` (report-only reconcile hook site).
- `bootstrap/lib/deploy.sh:101,144` — rsync merge/full modes (what "project would deploy" mirrors).
- `bootstrap/lib/common.sh:113-167` — `deploy_home_skills` Manifest-scoped prune (skills-only precedent the feature generalizes).
- `bootstrap/lib/common.sh:83-105` — `link_shared_assets` symlinks (FR-017/FR-015 basis).
- `configs/claude/scripts/branch_clean.sh:1-70` — err()/usage/`--help`/dry-run-default/`--apply`/`--yes`/`--json` + env-config conventions (verified).
- `configs/claude/scripts/smoke_test.py` — thin shim → `smoke_orchestrator.cli` (P-VI gate entry).
- `configs/claude/scripts/smoke_orchestrator/cli.py:24,83-85,171` — `_discover_apps(catalog_dir)`; "no catalogs found under {catalog_dir}" error; `--catalog-dir` flag (verified — default `smoke-catalog`).
- `configs/claude/scripts/smoke_orchestrator/executor.py:10,65-66,221` — Playwright imported lazily only for ui/api; empty selection ⇒ distinct EMPTY verdict (FR-008); `_test_status` (verified).
- `smoke-catalog/` — **does not exist** (verified `ls` → No such file or directory); this feature ships the first catalog.

**Risks.** No existing `smoke-catalog/` — CI must invoke `smoke_test.py` from the dir containing it (or pass `--catalog-dir`), wired to app `manifest`. Hermetic smoke requires the `--home`/`--project` overrides (hard design dependency — without them the cli step would mutate the runner's real `~/.claude`). realpath/readlink differs macOS vs Linux — fixtures + script must handle both. Active-dependent case must construct a live cross-home symlink to prove KEEP (false REMOVE risk if the link is resolved before the dependent check). Backup-location exclusion is recursion-sensitive — assert explicitly. pytest scope is conditional on factoring out the classifier.

---

## Topic 7 — Reuse-vs-new decision + final name

**Decision.** Ship as a NEW skill `deploy-reconcile` (`/deploy-reconcile`) wrapping new `configs/claude/scripts/deploy_reconcile.sh`, modeled on `branch-clean` (preview default, `--remove`+confirm+`--yes`, config-driven protection, Tier 1 on the destructive path). Do NOT extend sync-configs, health-check, deploy-drift-root-cause, `verify_installation`, or parallel_agent.py. Registry/doc work: (1) `.retired skill supply/skills/deploy-reconcile/SKILL.md` name+description frontmatter; (2) a `deploy-reconcile:` `tool_policies` block in `command_config.yml` (allowed Read/Glob/Grep/Bash; parallel_agents conditional; validation_tier 1; subagents never — copy branch-clean shape) — **protection DATA lives in `reconcile.yml`, not a command_config.yml block (Topic 2 / Verification)**; (3) NO `validation_criteria.yml` override (default Tier-1 weights, as branch-clean); (4) `docs/COMMANDS.md` + the platform-guide index are GENERATED from SKILL.md via `generate_commands_doc.py` (CI drift-checked) — run it, never hand-edit; (5) NO `labels.yml` change (issue/PR labels, unrelated); (6) wire the fail-open report-only deploy call (Topic 5); (7) add the bats test + register the smoke test (Topic 6).

**Rationale.** Each existing capability addresses a different concern and the destructive opt-in mode is contract-incompatible with the read-only diagnostics: sync-configs and health-check forbid Write/Edit/Task and are parallel_agents:never/tier-2 — adding `--remove` violates that contract and neither does a deployed-vs-project orphan compare. deploy-drift-root-cause is the INVERSE problem (state MISSING from a deploy) vs this (state EXTRA/orphaned). `verify_installation` only asserts a fixed required-files list is present. The closest prune (`deploy_home_skills` + `.deployed-skills`, gate_graphify_skill) is stateful, skills-only, single-root, with no KEEP/REMOVE/protection/backup/preview. branch-clean is the correct precedent (dry-run default, `--apply`+confirm, `--yes`, config-driven protected globs, tier 1, parallel_agents conditional). P-IV forecloses extending parallel_agent.py. Name `deploy-reconcile`: "reconcile" captures compare+classify better than clean/prune (removal-first connotation, wrong for a report-only-default tool) and pairs as the inverse of `deploy-drift-root-cause`.

**Alternatives considered.** Extend sync-configs / health-check — rejected (read-only forbidden-tool contract, tier-2, different concern). Extend `deploy_home_skills` prune — rejected (stateful, skills-only, single-root, no KEEP/REMOVE/backup/preview). Fold into deploy-drift-root-cause — rejected (inverse concern; merging analysis-triage with a destructive pruner loses the Tier-1 safety contract). Names `deploy-clean`/`prune-orphans`/`orphan-review` — rejected (removal-first connotation or omit the removal half); `reconcile-deploy` is an acceptable order-swap.

**Evidence.**
- `configs/claude/config/command_config.yml:407-418` — health-check forbids Write/Edit/Task, never, tier 2.
- `configs/claude/config/command_config.yml:440-454` — sync-configs forbids Write/Edit/Task, never, tier 2.
- `configs/claude/config/command_config.yml:507-517` — branch-clean: Bash, parallel_agents conditional "Tier 1 on the destructive --apply path", tier 1 (precedent shape).
- `configs/claude/config/command_config.yml:757-765` — `branch_clean` config block (model, but for reconcile the DATA goes to `reconcile.yml`).
- `configs/claude/scripts/branch_clean.sh:1-64` — flags + err() + bash 3.2 (verified).
- `bootstrap/lib/deploy.sh:414-447` — `verify_installation` only checks a fixed required-files list.
- `bootstrap/lib/common.sh:113-167` — `deploy_home_skills` stateful manifest prune; `:173-203` `gate_graphify_skill`.
- `.retired skill supply/skills/deploy-drift-root-cause/SKILL.md` — MISSING-state concern (inverse).
- `.retired skill supply/skills/sync-configs/SKILL.md`, `health-check/SKILL.md` — read-only diagnostics.
- `configs/claude/scripts/generate_commands_doc.py`, `command_catalog.py` — COMMANDS.md generated from SKILL.md frontmatter (drift-gated).
- `configs/claude/config/labels.yml` — issue/PR label registry (no change).

**Risks.** Backup location must be excluded from scope (`~/.manifest` is outside `~/.claude`) + hard-excluded by policy. Protection defaults must cover everything `restore_runtime_state` preserves or risk a false REMOVE (high blast radius) — gated by the live fixture. Symlink dedup must reconcile a shared target once and keep a still-linked target KEEP. Script language: bash 3.2-compatible with a portable realpath resolver. Deploy-time call must be fail-open (WARN, never abort) while bootstrap still exits non-zero on real failure.

---

## Verification

Adversarial review flagged 5 contradictions across the consolidated decisions. All resolved in this doc; the design now reads consistently across topics.

1. **Protection-policy data location + config var (MAJOR).** Decision 2 said dedicated `reconcile.yml` via `RECONCILE_CONFIG`; Decisions 5 & 6 said a top-level `deploy_reconcile:` block in `command_config.yml` via `DEPLOY_RECONCILE_CONFIG`. **Resolved → dedicated `configs/claude/config/reconcile.yml` + env `RECONCILE_CONFIG`** (Topic 2). It isolates the long protected list, auto-deploys via the existing `rsync config/` (deploy.sh:144), and is itself a project source so it can never be flagged as its own orphan. Topics 5 & 7 amended to drop the command_config.yml DATA block; only the `tool_policies` registration entry stays there (not in conflict).

2. **Trash-root variable (MAJOR, latent data-safety bug).** Decision 5 used `$MANIFEST_STATE_DIR/reconcile-trash/…`. **Verified**: `MANIFEST_STATE_DIR` is a plain top-level assignment (bootstrap.sh:67) and is **never exported** (grep finds no `export MANIFEST_STATE_DIR`); only `MANIFEST_STATE_ROOT` is exported/profile-written (auth.sh:241). A child reconcile process would expand it empty → an unwritable `/reconcile-trash/…`. **Resolved → `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash/<ts>/`** (Topics 3 & 5, matching Decisions 2/3); never reference `MANIFEST_STATE_DIR` from the script; verify the move succeeds before deleting source.

3. **Script filename (MAJOR).** Decisions 5/7 said `deploy_reconcile.sh`; Decision 6 said `reconcile_deploy.sh`, so the test + smoke harness pointed at a non-existent path. **Resolved → `deploy_reconcile.sh` everywhere**; test renamed `tests/bats/deploy_reconcile.bats`, smoke step runs `deploy_reconcile.sh` (matches the `/deploy-reconcile` skill + branch-clean symmetry).

4. **Hermetic fixture-home hook (MAJOR).** Decision 6 required an all-roots fixture override for SC-002 + the P-VI smoke gate, but Decision 5's CLI offered only `--project`/`--root` (single root). **Resolved → added `--home DIR` / `MANIFEST_RECONCILE_HOME` overriding the base for all five managed roots (default `$HOME`)** to Topic 5's CLI; bats and the Lite smoke run never touch the real `~/.claude`.

5. **Override env naming (MINOR).** Three knobs (`MANIFEST_RECONCILE_TRASH`, `--backup-dir`, `MANIFEST_RECONCILE_TS`). **Resolved → one surface: `--backup-dir` flag + `MANIFEST_RECONCILE_TRASH` env (trash root), plus `MANIFEST_RECONCILE_TS` as a documented test-only timestamp hook**; always keep the same-second collision suffix guard.

**Unsupported claims addressed.** (a) The live-machine realpath equalities and any foreign-dir names behind the Topic 1/4 dedup model are now re-asserted by the bats fixture rather than assumed; the structural basis (parent-dir symlinks) is grounded in `common.sh:88-105`. (b) The smoke-orchestrator citations were re-verified against actual code this pass: `cli.py:24/83-85/171` (`_discover_apps`, "no catalogs found" error, `--catalog-dir` default `smoke-catalog`) and `executor.py:10/65-66/221` (lazy Playwright for ui/api only, distinct EMPTY verdict, `_test_status`); `smoke-catalog/` confirmed absent (this feature ships the first catalog).
