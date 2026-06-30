# CLI Contract: `deploy_reconcile.sh` + `/deploy-reconcile`

> Feature: Deploy Reconciliation Review (Orphan Detection) — 368.
> Spec: `specs/368-deploy-orphan-review/spec.md`. Research: `specs/368-deploy-orphan-review/research.md`.
>
> This contract defines the user-facing surface of the reconcile script and its
> skill wrapper: command name, flags, inputs, stdout/preview format, `--json`
> schema, exit codes, and the confirm-before-remove + recoverable-backup
> behavior. It is the authoritative interface spec; implementation lives in
> `configs/claude/scripts/deploy_reconcile.sh` and the skill in
> `.skillshare/skills/deploy-reconcile/SKILL.md`.

---

## 1. Command name

| Surface | Name |
|---------|------|
| Script | `configs/claude/scripts/deploy_reconcile.sh` (deployed to `~/.claude/scripts/deploy_reconcile.sh`) |
| Skill | `/deploy-reconcile` (`.skillshare/skills/deploy-reconcile/SKILL.md`) |
| Deploy-time hook | `reconcile_deploy_report()` in `bootstrap/lib/deploy.sh`, called from `bootstrap.sh main()` after `deploy_configs` (preview-only, fail-open) |

Hyphen-skill / underscore-script symmetry mirrors `branch-clean` ↔ `branch_clean.sh`.

Implementation constraints: Bash, `set -euo pipefail`, bash 3.2-safe (macOS).
Portable realpath via `python3 os.path.realpath` (never `readlink -f`).
Canonical error helper: `err() { echo "deploy-reconcile: $*" >&2; }`.

---

## 2. Synopsis

```
deploy_reconcile.sh [--remove] [--yes] [--json]
                    [--project DIR] [--home DIR] [--root DIR]
                    [--config PATH] [--protect GLOB]...
                    [--backup-dir DIR] [--help]
```

Default invocation (no flags) = **read-only preview** of all five managed roots.

---

## 3. Flags

| Flag | Env equivalent | Default | Meaning |
|------|----------------|---------|---------|
| *(none)* | — | preview | Read-only preview: list KEEP/REMOVE orphans + summary. Makes **no** filesystem change (SC-002). |
| `--remove` | — | off | Destructive mode: move REMOVE orphans to the recoverable backup. Requires confirmation unless `--yes`. Never deletes KEEP items (FR-010/SC-005). |
| `--yes` | `RECONCILE_ASSUME_YES=1` | off | Non-interactive confirm for `--remove` (documented automation path, FR-010). Ignored without `--remove`. |
| `--json` | — | off | Emit the machine-readable report to stdout instead of the human preview (FR-004). Valid in both preview and `--remove` modes. |
| `--project DIR` | `MANIFEST_REPO` | auto-detect | Repo source root used to compute "what the project would deploy" (skills from `.skillshare/skills`, configs from `configs/claude` + `configs/<assistant>`, honoring `services.yml` toggles + graphify gating + merge/full mode). Auto-detects a git repo containing `configs/claude/` upward from the script location; **exit 2** if unresolved. |
| `--home DIR` | `MANIFEST_RECONCILE_HOME` | `$HOME` | Override the base for **all five** managed roots (`<DIR>/.claude`, `<DIR>/.cursor`, …). Testability hook for hermetic bats + the P-VI smoke gate; the real `~/.claude` is never touched in tests. |
| `--root DIR` | — | all 5 roots | Scope the review to a single managed root instead of all five. |
| `--config PATH` | `RECONCILE_CONFIG` | `$SCRIPT_DIR/../config/reconcile.yml` | Protection-policy file (flat glob list under `reconcile.protected:`). Resolves to `~/.claude/config/reconcile.yml` when deployed, repo copy when tested. |
| `--protect GLOB` | — | — | Repeatable. Add a protection glob for this run (additive; any match → KEEP). Unions with config + machine-local `reconcile.local.yml`. |
| `--backup-dir DIR` | `MANIFEST_RECONCILE_TRASH` | `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash` | Trash root for recoverable removal. Refuses (exit 2) if it resolves inside any managed root. |
| `--help` | — | — | Print usage (≤15 lines) and exit 0. MUST succeed before any config/home/dependency lookup. |

Test-only env (not a flag; documented for harness use): `MANIFEST_RECONCILE_TS`
overrides the backup timestamp; a same-second collision suffix guard always applies.

Protection precedence (additive union, only grows; any match → KEEP, no
negation per SC-004): (1) hardcoded guards (the trash dir + the reconcile config
files themselves), (2) `--protect` globs, (3) machine-local
`${MANIFEST_RECONCILE_CONFIG:-$MANIFEST_STATE_ROOT/reconcile.local.yml}`,
(4) deployed/source `reconcile.yml`.

---

## 4. Inputs

- **Deployed state** — the contents of the five managed roots under the resolved
  home base. Each deployable unit is enumerated (skills = top-level dirs under
  `<root>/skills`; config = individual files under `<root>/config`; per-home real
  artifacts such as `~/.cursor/rules/*.mdc`, `~/.gemini/GEMINI.md`,
  `~/.codex/AGENTS.md`). Units are canonicalized via `python3 os.path.realpath`
  and deduped by canonical path so a shared symlinked target is reported once
  (FR-017).
- **Project source** — resolved from `--project`/`MANIFEST_REPO`/auto-detect; the
  set of units the *current* project would deploy, honoring `services.yml`.
- **Protection policy** — `reconcile.yml` + `--protect` + machine-local overrides.
- **Dependent-edge index** — a bounded reverse-symlink scan
  (`find <home> -mindepth 1 -maxdepth 2 -type l`, ~20 edges) of only the four
  secondary homes, never a filesystem walk (FR-016).

A deployed unit is an **orphan** iff it sits in a managed root and has no current
project source. An orphan is **REMOVE-eligible** iff it matches no protection
pattern AND no active dependent edge resolves to/into it; otherwise **KEEP**.

---

## 5. Human-readable stdout (preview, default)

Each orphan prints on one line: a verdict tag, the canonical path (relative to
its managed root, prefixed with the root tag), and a short reason in parens.
KEEP lines first, then REMOVE, then a summary block.

```
deploy-reconcile: review of 5 managed roots (preview — no changes made)

KEEP   (3)
  ~/.claude/settings.local.json          (protected: user-owned settings)
  ~/.claude/.credentials.json            (protected: credential/auth file)
  ~/.claude/skills/legacy-helper         (shared target — active dependents: cursor, gemini)

REMOVE (2)
  ~/.claude/skills/old-skill             (orphan: no project source)
  ~/.claude/config/stale-layout.yml      (orphan: no project source)

Summary: 5 orphans  |  3 KEEP  |  2 REMOVE
Run with --remove to move the 2 REMOVE item(s) to a recoverable backup.
```

Clean state (FR-012):

```
deploy-reconcile: review of 5 managed roots (preview — no changes made)

Summary: 0 orphans  |  0 KEEP  |  0 REMOVE
Deployed environment matches the project. No orphans found.
```

Format rules:
- Verdict tags are exactly `KEEP` and `REMOVE`; counts appear in the section
  header `(N)` and again in the `Summary:` line.
- Paths are displayed `~/.<root>/<relative>` (tilde-abbreviated canonical path);
  the canonical `~/.claude` path is shown even for items reached via a secondary
  home (dedup, FR-017).
- Reason strings are stable, human-readable categories: `orphan: no project
  source`, `protected: <category>`, `shared target — active dependents: <homes>`.
- The advisory `Summary:` line is always printed last (before the call-to-action),
  even in `--remove` mode, so the deploy-time hook can grep one line (FR-005).

---

## 6. `--remove` mode output

`--remove` first prints the same KEEP/REMOVE preview, then the confirm gate, then
the per-item move report and backup location.

```
deploy-reconcile: review of 5 managed roots

KEEP   (3)
  ...
REMOVE (2)
  ~/.claude/skills/old-skill             (orphan: no project source)
  ~/.claude/config/stale-layout.yml      (orphan: no project source)

Summary: 5 orphans  |  3 KEEP  |  2 REMOVE
About to move 2 REMOVE item(s) to:
  ~/.manifest/reconcile-trash/20260630_011500/
Proceed? [y/N]
```

After confirmation (or `--yes`):

```
Moved: ~/.claude/skills/old-skill         -> reconcile-trash/20260630_011500/claude/skills/old-skill
Moved: ~/.claude/config/stale-layout.yml  -> reconcile-trash/20260630_011500/claude/config/stale-layout.yml

Removed 2 item(s). Recoverable backup:
  ~/.manifest/reconcile-trash/20260630_011500/
Restore with:
  ~/.manifest/reconcile-trash/20260630_011500/restore.sh
```

Declined confirmation (FR-010/FR-011 / US3-AC2):

```
deploy-reconcile: --remove requires confirmation. Nothing removed.
Re-run with --yes for non-interactive removal (or RECONCILE_ASSUME_YES=1).
```

---

## 7. `--json` output schema

`--json` writes a single JSON object to stdout (no human lines). Same shape in
preview and `--remove` modes; in preview, `removed` is `null` and `backup_dir` is
`null`.

```json
{
  "mode": "preview",
  "project": "/Users/me/Documents/GitHub/Manifest",
  "roots": ["~/.claude", "~/.cursor", "~/.gemini", "~/.codex", "~/.antigravity"],
  "summary": { "orphans": 5, "keep": 3, "remove": 2 },
  "items": [
    {
      "canonical_path": "$HOME/.claude/skills/old-skill",
      "display_path": "~/.claude/skills/old-skill",
      "root": "claude",
      "unit_type": "skill",
      "verdict": "REMOVE",
      "reason_code": "orphan_no_source",
      "reason": "orphan: no project source",
      "dependents": []
    },
    {
      "canonical_path": "$HOME/.claude/skills/legacy-helper",
      "display_path": "~/.claude/skills/legacy-helper",
      "root": "claude",
      "unit_type": "skill",
      "verdict": "KEEP",
      "reason_code": "shared_active_dependents",
      "reason": "shared target — active dependents: cursor, gemini",
      "dependents": ["cursor", "gemini"]
    },
    {
      "canonical_path": "/Users/me/.claude/settings.local.json",
      "display_path": "~/.claude/settings.local.json",
      "root": "claude",
      "unit_type": "config",
      "verdict": "KEEP",
      "reason_code": "protected",
      "reason": "protected: user-owned settings",
      "matched_pattern": "settings.local.json",
      "dependents": []
    }
  ],
  "removed": null,
  "backup_dir": null
}
```

Field contract:

| Field | Type | Notes |
|-------|------|-------|
| `mode` | string | `"preview"` or `"remove"`. |
| `project` | string | Resolved project root. |
| `roots` | array<string> | The managed roots reviewed (1 if `--root` given). |
| `summary.orphans` / `.keep` / `.remove` | int | Counts; `orphans == keep + remove`. |
| `items[]` | array<object> | One per deduped orphan. |
| `items[].canonical_path` | string | Absolute realpath; the dedup key. |
| `items[].display_path` | string | Tilde-abbreviated canonical path. |
| `items[].root` | string | Owning root tag: `claude`/`cursor`/`gemini`/`codex`/`antigravity`. |
| `items[].unit_type` | string | `"skill"` or `"config"`. |
| `items[].verdict` | string | `"KEEP"` or `"REMOVE"`. |
| `items[].reason_code` | string | Stable enum: `orphan_no_source`, `protected`, `shared_active_dependents`. |
| `items[].reason` | string | Human-readable reason. |
| `items[].matched_pattern` | string | Present only when `reason_code == "protected"`. |
| `items[].dependents` | array<string> | Secondary-home tags holding an active edge (empty unless `shared_active_dependents`). |
| `removed` | null \| array<object> | In `--remove`: `[{canonical_path, backup_path}]`; `null` in preview. |
| `backup_dir` | null \| string | In `--remove`: the timestamped trash dir; `null` in preview. |

---

## 8. Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success: preview produced, clean (no orphans), or removal completed. **Orphans-found NEVER yields nonzero** — the deploy-time report must not fail the deploy (FR-006/P-V). |
| 1 | Removal-action failure (a move failed / backup not writable / EXDEV copy unverified). |
| 2 | Usage error: bad flag, cannot resolve `--project`, or `--backup-dir` resolves inside a managed root. |

`--help` always exits 0. A missing `~/.claude` is not an error — it reports zero
orphans and exits 0 (FR-012 edge case).

---

## 9. Confirm-before-remove + recoverable-backup behavior

- **Preview is the default and is pure-read** (SC-002). Removal happens only with
  explicit `--remove` (FR-006/FR-011).
- **Confirm gate.** With `--remove`, the script prints the full REMOVE list and
  the target backup dir, then requires an affirmative answer read from
  `/dev/tty` (interactive) OR `--yes`/`RECONCILE_ASSUME_YES=1` (non-interactive,
  FR-010). Without confirmation, nothing is moved (US3-AC2).
- **Recoverable, never hard-delete.** REMOVE items are *moved* into a timestamped
  trash tree `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/reconcile-trash/<RUN_TS>/<home-tag>/<relative-path>/`
  (FR-010/SC-008). `RUN_TS=$(date +%Y%m%d_%H%M%S)` with a same-second suffix
  guard; test override `MANIFEST_RECONCILE_TS`.
- **Trash is outside managed scope** (`~/.manifest`), so a later review never
  re-reports a backup (spec edge case), reinforced by a default protection
  pattern. The script refuses (exit 2) a `--backup-dir` that resolves inside any
  managed root.
- **Atomic move + EXDEV fallback.** `mv` for same-filesystem atomicity; on EXDEV,
  `rsync -a` (preserves symlinks/attrs) then verified `rm` — copy success is
  asserted before the source is deleted (no data loss).
- **Restore artifacts.** The backup dir gets `removed.tsv` (one row per moved
  item: canonical path ⇥ backup path) and a generated `restore.sh` that moves
  each item back to its canonical `~/.claude` path first (so secondary symlinks
  re-resolve). Trash dir is `chmod 700`.
- **Removal acts on the canonical path only** — never through a secondary-home
  parent symlink — and only on REMOVE items; KEEP items are untouched (SC-005).
- **Shared targets with active dependents are KEEP** (FR-008/FR-015), so a prune
  can never dangle a secondary-home link.

---

## 10. Invocation examples

### Example 1 — On-demand preview (default, read-only)

```console
$ deploy_reconcile.sh --project ~/Documents/GitHub/Manifest
deploy-reconcile: review of 5 managed roots (preview — no changes made)

KEEP   (2)
  ~/.claude/settings.local.json   (protected: user-owned settings)
  ~/.claude/.credentials.json     (protected: credential/auth file)

REMOVE (1)
  ~/.claude/skills/old-skill      (orphan: no project source)

Summary: 3 orphans  |  2 KEEP  |  1 REMOVE
Run with --remove to move the 1 REMOVE item(s) to a recoverable backup.
$ echo $?
0
```

### Example 2 — JSON preview for tooling

```console
$ deploy_reconcile.sh --project ~/Documents/GitHub/Manifest --json
{"mode":"preview","project":"/Users/me/Documents/GitHub/Manifest",
 "roots":["~/.claude","~/.cursor","~/.gemini","~/.codex","~/.antigravity"],
 "summary":{"orphans":3,"keep":2,"remove":1},
 "items":[
   {"canonical_path":"/Users/me/.claude/skills/old-skill","display_path":"~/.claude/skills/old-skill",
    "root":"claude","unit_type":"skill","verdict":"REMOVE","reason_code":"orphan_no_source",
    "reason":"orphan: no project source","dependents":[]},
   {"canonical_path":"/Users/me/.claude/settings.local.json","display_path":"~/.claude/settings.local.json",
    "root":"claude","unit_type":"config","verdict":"KEEP","reason_code":"protected",
    "reason":"protected: user-owned settings","matched_pattern":"settings.local.json","dependents":[]}
 ],
 "removed":null,"backup_dir":null}
$ echo $?
0
```

### Example 3 — Non-interactive recoverable removal

```console
$ deploy_reconcile.sh --project ~/Documents/GitHub/Manifest --remove --yes
deploy-reconcile: review of 5 managed roots

REMOVE (1)
  ~/.claude/skills/old-skill   (orphan: no project source)

Summary: 3 orphans  |  2 KEEP  |  1 REMOVE
Moved: ~/.claude/skills/old-skill -> reconcile-trash/20260630_011500/claude/skills/old-skill

Removed 1 item(s). Recoverable backup:
  ~/.manifest/reconcile-trash/20260630_011500/
Restore with:
  ~/.manifest/reconcile-trash/20260630_011500/restore.sh
$ echo $?
0
```

### Example 4 — `--remove` without confirmation refuses (interactive, answered N)

```console
$ deploy_reconcile.sh --project ~/Documents/GitHub/Manifest --remove
deploy-reconcile: review of 5 managed roots

REMOVE (1)
  ~/.claude/skills/old-skill   (orphan: no project source)

Summary: 3 orphans  |  2 KEEP  |  1 REMOVE
About to move 1 REMOVE item(s) to:
  ~/.manifest/reconcile-trash/20260630_011500/
Proceed? [y/N] n
deploy-reconcile: --remove requires confirmation. Nothing removed.
Re-run with --yes for non-interactive removal (or RECONCILE_ASSUME_YES=1).
$ echo $?
0
```

### Example 5 — Cannot resolve project (deployed copy, no repo)

```console
$ ~/.claude/scripts/deploy_reconcile.sh
deploy-reconcile: cannot resolve project source; pass --project DIR or set MANIFEST_REPO
$ echo $?
2
```

---

## 11. Skill wrapper (`/deploy-reconcile`)

`SKILL.md` body is modeled on `branch-clean`, four sections:

1. **Preview** — run `deploy_reconcile.sh --project <repo>` (default), show the
   KEEP/REMOVE summary; explain managed scope and dedup.
2. **Apply with confirm** — only on explicit user request, run `--remove`
   (interactive confirm) or `--remove --yes` for automation; surface the backup
   path + `restore.sh`.
3. **Review outcome** — read back `removed.tsv` / summary; confirm KEEP items
   untouched.
4. **Safety** — preview-first, recoverable backup, never run `--remove` during a
   routine deploy (FR-006).

Registry: `tool_policies.deploy-reconcile` in `command_config.yml` (allowed
Read/Glob/Grep/Bash; `parallel_agents` conditional — Tier 1 on the `--remove`
path; `subagents` never). Protection DATA lives in `reconcile.yml`, not in
`command_config.yml`. No `validation_criteria.yml` override (default Tier-1
weights). `docs/COMMANDS.md` is regenerated from SKILL.md, never hand-edited.

Deploy-time: `bootstrap.sh main()` calls `reconcile_deploy_report ||
print_warning "reconcile review skipped (non-fatal)"` after `deploy_configs`,
running `deploy_reconcile.sh --project "$SCRIPT_DIR"` **preview-only** — never
`--remove`, never contributing to `verify_errors` (fail-open, P-V).
