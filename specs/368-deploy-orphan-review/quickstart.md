# Quickstart: Deploy Reconciliation Review (368)

> Hands-on verification walkthrough for `deploy_reconcile.sh` / the `/deploy-reconcile`
> skill. Builds a hermetic fake managed-home + fake project, then exercises preview,
> opt-in recoverable removal, restore, cross-home dedup, and the deploy-time
> report-only path. Every step maps to the FR/SC it verifies.
> Spec: `specs/368-deploy-orphan-review/spec.md` · Research: `specs/368-deploy-orphan-review/research.md`.

## Conventions used below

- `SCRIPT=configs/claude/scripts/deploy_reconcile.sh` (run from the repo root).
- Fixture base `SANDBOX` overrides the base of all five managed roots via
  `--home`/`MANIFEST_RECONCILE_HOME`, so **nothing touches your real `~/.claude`**.
- Trash root is set to `MANIFEST_RECONCILE_TRASH` (a.k.a. `--backup-dir`) under the
  fixture, outside every managed root.
- `MANIFEST_RECONCILE_TS` pins the backup timestamp so assertions are deterministic
  (test-only hook).
- Default invocation = **preview** (read-only). Removal requires `--remove` plus a
  confirm (`--yes` / `RECONCILE_ASSUME_YES=1`).

---

## Step 0 — Build the fixture (managed home + project)

Create a throwaway sandbox with a canonical `~/.claude`, the four secondary homes
symlinked into it (mirroring `link_shared_assets`' parent-dir links), and a fake
project source.

```bash
SANDBOX="$(mktemp -d)"
export MANIFEST_RECONCILE_HOME="$SANDBOX"
export MANIFEST_RECONCILE_TRASH="$SANDBOX/.manifest/reconcile-trash"
export MANIFEST_RECONCILE_TS="20260630_120000"
SCRIPT="configs/claude/scripts/deploy_reconcile.sh"

# --- Canonical managed home: ~/.claude ---
CLAUDE="$SANDBOX/.claude"
mkdir -p "$CLAUDE/skills" "$CLAUDE/config"

# (a) A LIVE skill (still in the project) — must be reconciled, never listed.
mkdir -p "$CLAUDE/skills/branch-clean"
echo "name: branch-clean" > "$CLAUDE/skills/branch-clean/SKILL.md"

# (b) ORPHAN skill-dir (deleted from project) — expected REMOVE.
mkdir -p "$CLAUDE/skills/dead-skill"
echo "name: dead-skill" > "$CLAUDE/skills/dead-skill/SKILL.md"

# (c) ORPHAN config file (older layout) — expected REMOVE.
echo "stale: true" > "$CLAUDE/config/old_layout.yml"

# (d) PROTECTED user file (local state/creds) — expected KEEP.
echo '{"token":"secret"}' > "$CLAUDE/.credentials.json"

# --- Secondary homes: parent-dir symlinks into ~/.claude (shared targets) ---
for home in .cursor .gemini .codex .antigravity; do
  mkdir -p "$SANDBOX/$home"
  ln -s "$CLAUDE/skills" "$SANDBOX/$home/skills"
  ln -s "$CLAUDE/config" "$SANDBOX/$home/config"
done

# --- Fake project source: only the LIVE skill exists upstream ---
PROJECT="$SANDBOX/repo"
mkdir -p "$PROJECT/.retired skill supply/skills/branch-clean" "$PROJECT/configs/claude/config"
echo "name: branch-clean" > "$PROJECT/.retired skill supply/skills/branch-clean/SKILL.md"
```

**Fixture inventory**

| Item | Lives at | Project source? | Protected? | Expected verdict |
|------|----------|-----------------|------------|------------------|
| `skills/branch-clean` | `~/.claude` (+4 links) | yes | – | not listed (reconciled) |
| `skills/dead-skill` | `~/.claude` (+4 links) | no | no | **REMOVE** |
| `config/old_layout.yml` | `~/.claude` (+4 links) | no | no | **REMOVE** |
| `.credentials.json` | `~/.claude` | no | yes | **KEEP** |

Verifies the **managed-scope** model (FR-009, FR-013) and **deployable-unit**
granularity — skill = whole top-level dir, config = per file (FR-018).

---

## Step 1 — Preview: KEEP / REMOVE report (no changes)

```bash
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT"
```

**Expected output (shape):**

```
deploy-reconcile: review of 5 managed roots (preview — no changes made)

KEEP   (1)
  ~/.claude/.credentials.json      (protected: credential/auth file)

REMOVE (2)
  ~/.claude/skills/dead-skill      (orphan: no project source)
  ~/.claude/config/old_layout.yml  (orphan: no project source)

Summary: 3 orphans  |  1 KEEP  |  2 REMOVE
Run with --remove to move the 2 REMOVE item(s) to a recoverable backup.
```

(Output format is canonical in [`contracts/reconcile-cli.md`](./contracts/reconcile-cli.md)
§5: KEEP section first, then REMOVE; tilde-abbreviated canonical paths; summary line
`Summary: N orphans  |  K KEEP  |  R REMOVE` — the deploy-time hook and bats greps key on
this exact wording.)

- `skills/branch-clean` is absent from the report (exists in project → reconciled).
- Exit code is **0** even with orphans present (orphans-found never yields nonzero).

Verifies: **FR-001** (compare deployed vs project), **FR-002** (KEEP/REMOVE +
reason), **FR-003** (on-demand preview), **FR-004** (summary counts), **FR-007 /
FR-014** (`.credentials.json` KEEP via protection policy), **SC-001** (list every
orphan in one run), **SC-007** ("noticed drift" → "previewed" with no change).

Confirm non-mutation explicitly (SC-002):

```bash
( cd "$SANDBOX" && find .claude .cursor .gemini .codex .antigravity | sort ) > /tmp/before.txt
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" >/dev/null
( cd "$SANDBOX" && find .claude .cursor .gemini .codex .antigravity | sort ) > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo "UNCHANGED (SC-002 OK)"
```

Verifies: **SC-002** (preview leaves the deployed env byte-for-byte unchanged).

Machine-readable variant (FR-004):

```bash
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" --json
```

---

## Step 2 — Cross-home dedup (shared/symlinked target reported once)

The same `dead-skill` orphan is reachable from `~/.claude` and all four secondary
homes (their `skills/` dirs symlink into `~/.claude/skills`). The report keys by
canonical (`realpath`) path, so it appears **exactly once**:

```bash
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" | grep -c 'dead-skill'
# => 1  (not 5)
```

Verifies: **FR-017** (resolve symlinks + dedup; shared target reconciled once,
single verdict, no conflicting dispositions across roots).

> Active-dependent safety (FR-008 / FR-015): if you instead delete `branch-clean`
> from the project so only the canonical leaf is orphaned while a secondary home
> still links the **parent** `skills/` dir, removal targets the canonical leaf and
> the surviving parent-level link never dangles. A namespace-level shared target with
> a live dependent edge is held **KEEP** with a reason naming the dependent home(s).

---

## Step 3 — Opt-in removal (only REMOVE items moved to backup)

Removal is gated: `--remove` alone (no confirm) does nothing.

```bash
# 3a. Gating: no opt-in -> nothing removed, told how to opt in.
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" --remove </dev/null
test -d "$CLAUDE/skills/dead-skill" && echo "still present (FR-011 OK)"
```

Verifies: **FR-011** (default non-destructive; removal needs explicit opt-in),
US3 acceptance #2.

```bash
# 3b. Explicit non-interactive opt-in.
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" --remove --yes
```

**Expected:**

```
deploy-reconcile: removed 2 orphan(s) -> recoverable backup
  skills/dead-skill        -> .manifest/reconcile-trash/20260630_120000/claude/skills/dead-skill
  config/old_layout.yml    -> .manifest/reconcile-trash/20260630_120000/claude/config/old_layout.yml
Restore with: <backup>/restore.sh
```

Assert the outcome — REMOVE gone, KEEP and LIVE untouched, backup populated:

```bash
TRASH="$MANIFEST_RECONCILE_TRASH/$MANIFEST_RECONCILE_TS"
test ! -e "$CLAUDE/skills/dead-skill"      && echo "REMOVE: dead-skill gone"
test ! -e "$CLAUDE/config/old_layout.yml"  && echo "REMOVE: old_layout.yml gone"
test -f "$CLAUDE/.credentials.json"        && echo "KEEP: credentials untouched (SC-005)"
test -d "$CLAUDE/skills/branch-clean"      && echo "LIVE: branch-clean untouched"
test -e "$TRASH/claude/skills/dead-skill"  && echo "BACKUP: dead-skill recoverable (SC-008)"
test -f "$TRASH/removed.tsv" && test -x "$TRASH/restore.sh" && echo "BACKUP: manifest + restore.sh present"
```

Verifies: **FR-010** (preview-first, explicit confirm / documented non-interactive
`--yes` path, recoverable timestamped backup, location reported), **SC-005** (only
REMOVE removed, 0 KEEP affected), **SC-008** (every removed item recoverable),
US3 acceptance #1 and #3.

---

## Step 4 — Restore from backup

```bash
"$TRASH/restore.sh"
test -d "$CLAUDE/skills/dead-skill"        && echo "RESTORED: dead-skill"
test -f "$CLAUDE/config/old_layout.yml"    && echo "RESTORED: old_layout.yml"
```

Restores canonical `~/.claude` paths first so any secondary-home parent links
re-resolve cleanly.

Verifies: **SC-008** (100% of removed items retrievable from the reported backup),
**FR-010** (recoverable, not hard-deleted).

---

## Step 5 — Backup excluded from scope (no re-report)

Remove again, then run a fresh preview: the trash tree lives under
`$SANDBOX/.manifest`, **outside** every managed root, so it is never re-scanned.

```bash
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" --remove --yes >/dev/null
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT" | grep -c 'reconcile-trash'
# => 0  (backed-up items are never re-flagged)
```

Verifies: edge case "Removal backup location" (backup excluded / protected),
**FR-009** (only managed scope acted on), structural self-exclusion (`~/.manifest`
out of scope).

---

## Step 6 — Deploy-time report-only path (fail-open)

The deploy step calls `deploy_reconcile.sh ... ` in **preview only** via
`reconcile_deploy_report()` (in `bootstrap/lib/deploy.sh`), invoked from
`bootstrap.sh main()` after `deploy_configs`. It prints the KEEP/REMOVE summary,
never removes, and is fail-open (a reconcile error WARNs but the deploy succeeds).

Simulate the report-only invocation against the (re-restored) fixture:

```bash
"$TRASH/restore.sh" 2>/dev/null || true   # repopulate orphans
# Same call the deploy makes — preview, no --remove:
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT"
echo "deploy-report exit: $?"   # 0 — advisory only, never fails the deploy

# No backup dir is created by a report-only run:
test ! -d "$MANIFEST_RECONCILE_TRASH/report-only-check" && echo "report-only created no backup"
```

Fail-open check (forced error must WARN, not abort) — the guarded call in
`main()` is `reconcile_deploy_report || print_warning "reconcile review skipped (non-fatal)"`:

```bash
"$SCRIPT" --home "$SANDBOX" --project "$SANDBOX/does-not-exist"; echo "exit: $?"
# exit 2 (cannot resolve project) — the bootstrap guard turns this into a WARN,
# deploy continues, and it never contributes to verify_errors.
```

Verifies: **FR-005** (review runs as part of deploy + surfaces summary), **FR-006**
(deploy entry point is report-only, deletes nothing), US2 acceptance #1–#3,
**SC-006** (summary on every deploy, no perceptible delay, bounded ~20-edge scan),
P-V fail-open.

---

## Step 7 — Clean-state and empty-home edge cases

```bash
# Clean state: deploy the orphans away (or restore none) and re-preview.
rm -rf "$CLAUDE/skills/dead-skill" "$CLAUDE/config/old_layout.yml"
"$SCRIPT" --home "$SANDBOX" --project "$PROJECT"
# => "no orphans" / Summary: 0 orphans

# Missing managed home: zero orphans, exit 0 (no error).
EMPTY="$(mktemp -d)"
"$SCRIPT" --home "$EMPTY" --project "$PROJECT"; echo "exit: $?"
```

Verifies: **FR-012** (clear "no orphans" result), edge cases "Empty or missing
deployed location" (reports zero rather than erroring).

---

## Teardown

```bash
rm -rf "$SANDBOX" "$EMPTY"
unset MANIFEST_RECONCILE_HOME MANIFEST_RECONCILE_TRASH MANIFEST_RECONCILE_TS
```

---

## FR / SC coverage map

| Step | Verifies |
|------|----------|
| 0 Fixture | FR-009, FR-013, FR-018 |
| 1 Preview | FR-001, FR-002, FR-003, FR-004, FR-007, FR-014; SC-001, SC-002, SC-007 |
| 2 Dedup | FR-017 (+ FR-008/FR-015 note) |
| 3 Removal | FR-010, FR-011; SC-005, SC-008 |
| 4 Restore | FR-010; SC-008 |
| 5 Backup excluded | FR-009; backup-location edge case |
| 6 Deploy-time | FR-005, FR-006; SC-006; P-V fail-open |
| 7 Edge cases | FR-012; empty/missing-home edge case |
