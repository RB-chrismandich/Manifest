# skillshare Centralized Setup — Design

**Date**: 2026-05-30
**Status**: Approved for planning
**Topic**: Adopt `skillshare` (runkids, v0.19.24) as the centralized skill
library + supply-chain layer for the Manifest repo, cloned across machines and
synced to multiple AI CLI tools — as an **enhancement** over Manifest's
existing bootstrap deployment, not a hard dependency in it.

---

## Goal

Use `skillshare` as a git-backed, centralized skill library that is:

1. **Cloned on multiple machines** — the Manifest repo is the central source.
2. **Synced across multiple tools** — Claude, Copilot, Cursor, Gemini, Codex,
   Antigravity.

### What skillshare is (and isn't) here

skillshare's durable value is as a **package manager + auditor** for the skill
library (`audit`, `search`, `install <repo>`, `update`, `check`) — the
supply-chain layer Manifest's bash bootstrap will never have. Its `sync`
(deployment) is roughly a lateral move over Manifest's existing symlink
fan-out, so:

- skillshare is the **source of truth + supply-chain** layer.
- External skills (e.g. `runkids/ai-hooks-integration`) are pulled via
  `skillshare install <repo>`, audited, tracked for updates, and synced
  alongside the hand-authored skills (§7).
- `skillshare sync` is the **preferred** deployment step.
- bootstrap's existing **symlink deploy remains a fallback**, so skillshare is
  an enhancement, **never a single point of failure**. A fresh machine without
  skillshare (or with a broken skillshare) still gets its skills.

`bootstrap.sh` keeps owning machine setup (CLIs, configs, MCP) and delegates
skill deployment to skillshare *when present*, falling back otherwise.

## Current State

| Thing | Location | Notes |
|-------|----------|-------|
| 27 canonical skills | `configs/claude/skills/` | Deployed to `~/.claude/skills/` by `bootstrap.sh` today |
| skillshare source | `.skillshare/skills/` | Empty (project mode, just `init`ed) |
| skillshare source | `.skillshare/agents/` | Empty |
| skillshare config | `.skillshare/config.yaml` | targets: `claude`, `copilot` (project-relative paths); **git-ignored** |
| Manifest references to `configs/claude/skills` | ~20+ files | bootstrap, `generate_cursor_rules.sh` (`SKILLS_DIR`), `AGENTS.md`, docs, several `SKILL.md` |

Problems to fix: (a) skillshare source is empty while real skills live
elsewhere; (b) targets point inside the repo, not at live tool dirs; (c)
`config.yaml` is git-ignored so target definitions would not replicate to a
fresh clone.

## Design

### 1. Single source of truth (symlink migration)

- Physically move the 27 skill directories from `configs/claude/skills/` into
  `.skillshare/skills/`. skillshare becomes the single owner of skill content.
- Replace `configs/claude/skills` with a **relative symlink** →
  `../../.skillshare/skills`.
- **Why symlink, not hard move:** `configs/claude/skills` is referenced in
  ~20+ places. The symlink keeps every reference, the `generate_cursor_rules.sh`
  `SKILLS_DIR`, and the cursor/gemini/codex symlink chain resolving unchanged,
  while skillshare owns the real files. Minimal diff, zero broken references.
- `README.md` currently inside `configs/claude/skills/` moves with the skills
  into `.skillshare/skills/`.

**Consumer traversal rule (post-symlink).** The `configs/claude/skills` symlink
exists for backward-compat with human-facing references only. Automation must
read the **physical** `.skillshare/skills/`:

- **Shell globbing is safe** through the symlink. Verified: `generate_cursor_rules.sh:34`
  uses `for skill_dir in "$SKILLS_DIR"/*/` — pathname expansion resolves through
  the `skills` symlink into `.skillshare/skills/` with no `-L` needed. No change
  required to that script.
- **`find <path>` and Python `os.walk(<path>)` are NOT safe** over a symlinked
  start dir without `-L` / `followlinks=True`. Repo grep found no such traversal
  of the skills dir today (other references are markdown/echo strings), but new
  automation MUST target `.skillshare/skills/` directly or pass `-L`.

### 2. Targets honor Manifest's symlink architecture

Manifest's existing pattern: `~/.claude/skills` is the **one real location** on
a machine; other tools read it via per-tool symlinks created by bootstrap. We
extend that rather than copying six duplicate trees.

> **Tooling constraint (verified 2026-05-30):** skillshare does **not** expand
> `~` or env vars in a target `skills.path`. A dry-run with `path: ~/.claude/skills`
> creates a literal `~` directory under the repo
> (`/tmp/ss_test.../~/.claude/skills`). An absolute path *works* but is
> user/machine-specific, so it cannot live in a committed, replicated
> `config.yaml`. **Conclusion:** skillshare cannot portably deploy to home. The
> home deploy is therefore owned by **bootstrap**, not skillshare. skillshare is
> used only for project-relative targets (Copilot) plus the supply-chain
> lifecycle.

- **bootstrap copies the physical `.skillshare/skills/` → `~/.claude/skills`**
  (the canonical machine location). No skillshare home target; no `~`-expansion
  dependency; works identically on every machine/user.
- **bootstrap-created symlinks** → `~/.claude/skills`:
  - `~/.cursor/skills` (already)
  - `~/.gemini/skills` (already)
  - `~/.codex/skills` (already)
  - `~/.antigravity/skills` (**new** — add to bootstrap symlink set)
- **skillshare sync target — `copilot` → `.github/skills`** (project-relative;
  Copilot is project-scoped, so a repo-relative path is correct *and* portable —
  no `~` needed). **Implication:** Copilot sees these skills while working
  *inside the Manifest clone*. Acceptable, recorded constraint. If skillshare is
  absent, Copilot's project skills simply aren't synced (Copilot is optional and
  project-scoped) — home deploy is unaffected.

Net: **bootstrap** owns the one real home copy (`~/.claude/skills`) +
Cursor/Gemini/Codex/Antigravity symlinks. **skillshare** owns the project-scoped
Copilot sync (`.github/skills`) and the supply-chain lifecycle. No tool writes a
duplicate home tree, and nothing depends on skillshare expanding `~`.

### 3. Commit the skillshare config

- Edit `.skillshare/.gitignore`: remove `config.yaml` from the managed block so
  target definitions are committed and replicate to every clone. Keep `logs/`,
  `trash/`, `backups/` ignored.
- Commit `config.yaml` and the populated `.skillshare/skills/` tree.
- **Drift guard (docs).** Add a note to the repo's contributor docs that
  committed `config.yaml` is central Manifest skill infrastructure — edit it
  only when intentionally changing the shared setup, to avoid per-clone drift.

### 4. bootstrap integration (phased)

bootstrap is the **sole home deployer** (skillshare cannot portably target home —
see §2 constraint). skillshare never writes `~/.claude/skills`, so there is no
"skillshare-vs-fallback" branch for home deploy: bootstrap *always* copies the
physical `.skillshare/skills/`. skillshare's `sync` is invoked separately, only
to populate the project-relative Copilot target, and only when present.

**Step A — prove the pieces by hand.** Migrate, fix targets/config, and verify
deployment on this machine before bootstrap changes. Runbook (note: `skillshare
init` is **already done** — do NOT re-init, it can reset `config.yaml`):

1. **Migrate** — move the 27 dirs into `.skillshare/skills/`; create the
   relative symlink; verify with `ls -l configs/claude/skills` showing
   `-> ../../.skillshare/skills`.
2. **Config** — set `copilot` target to project-relative `.github/skills`;
   un-ignore `config.yaml`.
3. **Copilot dry run** — `skillshare sync --dry-run`; confirm it writes the
   repo-relative `.github/skills` (and NOT a literal `~`).
4. **Copilot sync** — `skillshare sync`; confirm `.github/skills` populated.
5. **External skill** — `skillshare install github.com/runkids/ai-hooks-integration`
   (audit gate), then `skillshare sync` again to include it.
6. **Home deploy by hand** — `cp -R .skillshare/skills/. ~/.claude/skills/`;
   confirm 28 real dirs (27 + ai-hooks-integration) in `~/.claude/skills`.

**Step B — wire bootstrap.** Once the pieces are proven, bootstrap's
`deploy_configs` becomes:

```
# 1. Generic config copy, EXCLUDING skills (the relative symlink must not be
#    copied verbatim — see below). Replaces `cp -R "$source_dir"/*`.
rsync -av --exclude 'skills' "$source_dir"/ "$TARGET_DIR"/

# 2. Home skills deploy — ALWAYS bootstrap, ALWAYS from the physical dir.
mkdir -p "$TARGET_DIR/skills"
rsync -av --delete "$SCRIPT_DIR/.skillshare/skills/" "$TARGET_DIR/skills/"

# 3. Tool symlinks (run AFTER ~/.claude/skills exists, else create_symlink skips):
#    cursor/gemini/codex already via link_shared_assets; add antigravity.
~/.antigravity/skills -> ~/.claude/skills   (NEW)

# 4. Project-scoped Copilot sync — only when skillshare is present:
if command -v skillshare >/dev/null && [ -f .skillshare/config.yaml ]; then
    skillshare sync     # populates .github/skills; no effect on home deploy
fi
```

Key constraints:

- **Carve skills out of the generic copy.** `deploy.sh:69` runs
  `cp -R "$source_dir"/* "$TARGET_DIR/"`. With `configs/claude/skills` as a
  *relative* symlink (`../../.skillshare/skills`), `cp -R` copies the **symlink
  itself** into `~/.claude/`, where it resolves to a non-existent
  `~/.skillshare/skills` — a guaranteed broken link on both BSD and GNU cp.
  Switching the generic copy to `rsync -av --exclude 'skills'` removes the
  symlink from the copy entirely; `deploy.sh` already uses `rsync -av
  --ignore-existing` (line 42), so this is consistent with the file's idiom.
- **Home deploy always sources the physical dir.** Step 2 copies from
  `$SCRIPT_DIR/.skillshare/skills/` directly (never via the compat symlink), so
  it is robust regardless of host symlink handling and independent of skillshare.
- **Strict ordering.** `mkdir -p "$TARGET_DIR/skills"` + the physical copy run
  *before* `link_shared_assets`, because `create_symlink` (common.sh:103) skips
  with a warning when its target does not exist — so the tool symlinks would be
  silently dropped if `~/.claude/skills` were not populated first.
- **skillshare is never load-bearing.** It is not required, not auto-installed
  as a blocker; bootstrap may *offer* `brew install skillshare`. If absent, home
  deploy is unaffected and only the project-scoped Copilot sync is skipped (with
  a notice).
- The same merge-mode path (`deploy.sh:42`, option 2) must apply the identical
  skills carve-out + physical home copy so merge installs behave consistently.

### 5. Multi-machine flow

```
git clone <Manifest remote>
cd Manifest
./bootstrap.sh        # installs CLIs, deploys configs (skills excluded from the
                      # generic copy), copies .skillshare/skills/ -> ~/.claude/skills,
                      # creates per-tool symlinks, then `skillshare sync` (Copilot)
                      # if skillshare is present
```

The Manifest git remote IS the central repo. skillshare's own `push`/`pull`
git-remote feature is **not** used — normal Manifest git handles replication.
Because bootstrap owns the home copy directly, a machine that never installs
skillshare still ends up fully configured (only project-scoped Copilot sync is
skipped).

### 6. Agents — out of scope (YAGNI)

`.skillshare/agents/` stays empty. Manifest has no agents directory today;
adding agent distribution is deferred until there are agents to distribute.

### 7. External tracked skill: `ai-hooks-integration`

The first concrete exercise of skillshare's package-manager role. `runkids/ai-hooks-integration`
is itself a skill (same author) that manages lifecycle hooks across AI tools
(Claude `~/.claude/settings.json`, Gemini `~/.gemini/settings.json`, Cursor
`~/.cursor/hooks.json`, OpenCode plugins). It ships `scripts/install_all.py` to
wire a given hook command into all supported tools at once. Requires Python 3.9+.

**Scope here:** install it as a *tracked external skill* and sync it — make it
available in the library, wired in when a repo needs it. Do **not** bind a
specific hook command yet (none specified; that is deferred until there is a
concrete hook to deploy).

```bash
skillshare install github.com/runkids/ai-hooks-integration   # audited on install
skillshare sync                                              # fan out like any skill
```

- **Audited on install.** `block_threshold: CRITICAL` in `config.yaml` gates the
  install; an external skill that trips a CRITICAL finding is blocked.
- **Tracked vs local.** It lands in `.skillshare/skills/ai-hooks-integration` as
  a skill *tracked to its upstream repo* (updatable via `skillshare check` /
  `skillshare update`), coexisting with the 27 hand-authored *local* skills. Both
  are committed to Manifest.
- **Coverage gap (recorded).** It supports Claude / Gemini / Cursor / OpenCode —
  **not** Copilot, Codex, or Antigravity. Its hook coverage is narrower than our
  skill-sync target set; that is expected, not a defect.
- **Settings overlap (recorded).** It edits `~/.claude/settings.json`; Manifest
  deploys `~/.claude/settings.local.json`. Different files, but both are Claude
  settings — we rely on its documented idempotent merge and verify no clobber.
- **Hook wiring deferred (runbook).** When a hook is needed:
  `~/.claude/skills/ai-hooks-integration/scripts/install_all.py --command <path> --name <name>`
  (preview with `--dry-run`; remove with `remove_all.py`). Not run during setup.
  Gate this step (NOT bootstrap's critical path — installing/syncing the skill
  runs no Python) with a Python 3.9+ pre-flight check:

  ```bash
  if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"; then
    echo "ai-hooks-integration hook wiring requires Python 3.9+ — skipping."
  fi
  ```

## Out of Scope

- skillshare hubs, web UI (`ui`), TUI mode.
- skillshare's native git `push`/`pull` (Manifest git covers it).
- Agent distribution.
- Migrating away from `bootstrap.sh` (it stays; skillshare slots into it).
- Wiring a concrete hook command via `ai-hooks-integration`'s `install_all.py`
  (the skill is installed/synced; binding a specific hook is deferred until one
  is specified — §7).

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| skillshare doesn't follow the `configs/claude/skills` symlink when reading source | Source is `.skillshare/skills/` (real dir); the symlink is only for backward-compat *consumers*, not skillshare's source. No risk to skillshare. |
| skillshare can't portably target `~/.claude/skills` (no `~` expansion; absolute paths aren't replicable) | bootstrap owns the home copy directly from physical `.skillshare/skills/`; skillshare only handles the project-relative Copilot target (§2, §4). Verified by dry-run 2026-05-30. |
| `cp -r configs/claude/*` copies the skills symlink and breaks it | Generic copy switched to `rsync -av --exclude 'skills'`; home skills copied separately from the physical dir (§4). |
| Antigravity real skills-dir path unknown | Antigravity rides the symlink (`~/.antigravity/skills -> ~/.claude/skills`); if Antigravity expects a different path, adjust the symlink target name only. |
| `config.yaml` re-managed by skillshare and re-added to `.gitignore` on upgrade | Note in repo docs; re-check `.skillshare/.gitignore` after `skillshare upgrade`. |
| Fresh machine lacks `skillshare` binary | Non-blocking: bootstrap drops to the symlink fallback and deploys skills anyway; skillshare stays optional. |
| Pre-1.0 tool (v0.19, single maintainer) breaks or changes behavior | skillshare is an enhancement layer, not load-bearing; the fallback deploy keeps machines working independent of skillshare. |
| `cp -R configs/claude/*` copies the relative skills symlink into `~/.claude/`, producing a broken link (`~/.skillshare/skills` does not exist) | Exclude `skills` from `deploy_configs`'s generic copy; deploy skills via a dedicated step that sources the physical `.skillshare/skills/` (§4). |
| Tool symlinks or `[ -d ~/.claude/skills ]` guards created before the skills dir exists | Unconditional `mkdir -p ~/.claude/skills` baseline before symlinks and before `skillshare sync` (§4). |
| CI/CD or linting on bare environments (no skillshare, may not traverse symlinks) | All validation/automation reads the physical `.skillshare/skills/`; `configs/claude/skills` is a backward-compat layer only. Shell globs are symlink-safe; `find`/`os.walk` callers must use `-L`/`followlinks` or target the physical dir. |
| `ai-hooks-integration` edits `~/.claude/settings.json`, which could clobber Manifest's settings | Different file from Manifest's `settings.local.json`; rely on its documented idempotent merge and verify (`--dry-run`) before any real hook wiring. Hook wiring is deferred (§7), so no edit happens during setup. |
| `ai-hooks-integration` needs Python 3.9+ on the host | bootstrap already installs Node/tooling; add a Python 3.9+ check before any `install_all.py` use. Install of the skill itself does not require running it. |
| External skill trips the audit (or upstream changes maliciously on update) | `block_threshold: CRITICAL` blocks install/update of a flagged skill; `skillshare check` surfaces upstream changes before `update` applies them. |

## Success Criteria

1. `skillshare status` shows the migrated skills in source and the `copilot`
   target pointing at project-relative `.github/skills`.
2. **bootstrap home deploy:** `./bootstrap.sh` copies `.skillshare/skills/` →
   `~/.claude/skills` (real dirs, no broken symlink); Cursor, Gemini, Codex,
   Antigravity see them via symlink.
3. `configs/claude/skills` resolves (symlink) and all existing references /
   `generate_cursor_rules.sh` still work.
4. `config.yaml` is committed; a fresh clone + `./bootstrap.sh` reproduces the
   full setup with skills in `~/.claude/skills` and fan-out symlinks.
5. **skillshare-absent verified:** with `skillshare` absent (or PATH-hidden),
   `./bootstrap.sh` still deploys all skills to `~/.claude/skills` via the
   physical-dir copy; only the project-scoped Copilot sync is skipped.
6. **Ordering verified:** on a clean run, `~/.claude/skills` is populated before
   any tool symlink is created; `~/.antigravity/skills` resolves to it.
7. **Copilot sync verified:** `skillshare sync` writes the repo-relative
   `.github/skills` (no literal `~` dir created).
8. **External skill verified:** `skillshare install github.com/runkids/ai-hooks-integration`
   passes audit, lands in `.skillshare/skills/ai-hooks-integration` as a tracked
   skill, is committed, and is included in the home deploy. No hook is wired
   (deferred).
9. `git status` is clean of unintended deletions; existing tests
   (`bats tests/bats/`, `pytest tests/python/`) still pass.
