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

- **skillshare copy target — `claude` → `~/.claude/skills`** (the canonical
  machine location; absolute/home-relative so it works on any machine).
- **bootstrap-created symlinks** → `~/.claude/skills`:
  - `~/.cursor/skills` (already)
  - `~/.gemini/skills` (already)
  - `~/.codex/skills` (already)
  - `~/.antigravity/skills` (**new** — add to bootstrap symlink set)
- **skillshare copy target — `copilot`** → Copilot's real skills dir. Copilot
  does not follow the `~/.claude/skills` symlink convention, so it gets its own
  copy target. Exact path to be confirmed against Copilot CLI docs during
  implementation (project-mode default is `.github/skills`; the global/home
  equivalent will be verified before wiring).
  - **If Copilot resolves skills project-scoped only** (its ecosystem leans on
    the active workspace's `.github/skills` rather than a home dir), keep the
    `copilot` target pointed at the repo-local `.github/skills`. **Implication:**
    Copilot then sees these skills only while working *inside the Manifest
    clone*, not machine-globally. Acceptable tool limitation; recorded here so
    it is a known constraint, not a surprise.

Net: skillshare manages two real copy destinations (`claude`, `copilot`);
Cursor/Gemini/Codex/Antigravity get the same skills for free via symlink.

### 3. Commit the skillshare config

- Edit `.skillshare/.gitignore`: remove `config.yaml` from the managed block so
  target definitions are committed and replicate to every clone. Keep `logs/`,
  `trash/`, `backups/` ignored.
- Commit `config.yaml` and the populated `.skillshare/skills/` tree.

### 4. bootstrap integration (phased, with fallback)

Rolled out in two steps so the migration is verified before bootstrap's deploy
path changes, and structured so skillshare is never load-bearing.

**Step A — prove sync standalone.** Migrate, fix targets/config, and verify
`skillshare sync` correctly populates `~/.claude/skills` by hand on this
machine. bootstrap is unchanged in this step.

**Step B — delegate-when-present, fall back otherwise.** Once sync is proven,
bootstrap's skill-deploy becomes:

```
# Baseline (always, before symlinks and before sync):
mkdir -p ~/.claude/skills

# Skills are EXCLUDED from the generic `cp -R configs/claude/* ~/.claude/`
# (deploy.sh:69) so the relative skills symlink is never copied verbatim.
if skillshare is installed and .skillshare/config.yaml exists:
    skillshare sync                                  # preferred path
else:
    cp -R .skillshare/skills/. ~/.claude/skills/      # fallback: PHYSICAL dir

# Per-tool symlinks (created AFTER ~/.claude/skills exists):
~/.cursor/skills  -> ~/.claude/skills   (existing)
~/.gemini/skills  -> ~/.claude/skills   (existing)
~/.codex/skills   -> ~/.claude/skills   (existing)
~/.antigravity/skills -> ~/.claude/skills   (NEW)
```

Key constraints surfaced by code review:

- **Carve skills out of the generic copy.** `deploy.sh:69` runs
  `cp -R "$source_dir"/* "$TARGET_DIR/"`. With `configs/claude/skills` as a
  *relative* symlink (`../../.skillshare/skills`), `cp -R` copies the **symlink
  itself** into `~/.claude/`, where it resolves to a non-existent
  `~/.skillshare/skills` — a guaranteed broken link on both BSD and GNU cp.
  `deploy_configs` MUST exclude `skills` from the generic copy in BOTH the
  skillshare-present and fallback paths.
- **Fallback sources the physical dir.** The fallback copies from
  `.skillshare/skills/` directly (not via the compat symlink), so it works even
  if the symlink layer is mishandled by the host toolchain.
- **Strict ordering.** `mkdir -p ~/.claude/skills` is an unconditional baseline
  that runs *before* any tool symlink and *before* `skillshare sync`, so
  symlink targets and `[ -d ~/.claude/skills ]` guards never see a missing dir.
- bootstrap **does not hard-require** skillshare and does not auto-install it as
  a blocker. It may *offer* to install it (Homebrew: `brew install skillshare`),
  but a missing skillshare only drops to the fallback with a clear notice.
- bootstrap adds the `~/.antigravity/skills → ~/.claude/skills` symlink to its
  existing per-tool symlink routine (needed by both paths).
- Net behavior is identical whether or not skillshare is present: all 27 skills
  land in `~/.claude/skills` and fan out via symlink.

### 5. Multi-machine flow

```
git clone <Manifest remote>
cd Manifest
./bootstrap.sh        # installs CLIs, deploys configs, creates per-tool
                      # symlinks, then `skillshare sync` if present else
                      # falls back to symlink deploy
```

The Manifest git remote IS the central repo. skillshare's own `push`/`pull`
git-remote feature is **not** used — normal Manifest git handles replication.
Because deployment falls back to symlinks, a machine that never installs
skillshare still ends up fully configured.

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
| `cp -r configs/claude/*` in bootstrap follows the symlink and double-deploys skills | bootstrap's skill deploy is gated: `skillshare sync` when present, else the existing symlink deploy — never both (§4). |
| Copilot/Antigravity real skills-dir path unknown | Verify against each tool's docs before wiring; project default `.github/skills` is the known-good fallback for Copilot. |
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

1. `skillshare status` shows 27 skills in source and `claude`/`copilot` targets
   pointing at live tool dirs.
2. `skillshare sync` populates `~/.claude/skills` with all 27 skills; Cursor,
   Gemini, Codex, Antigravity see them via symlink.
3. `configs/claude/skills` resolves (symlink) and all existing references /
   `generate_cursor_rules.sh` still work.
4. `config.yaml` is committed; a fresh clone + `./bootstrap.sh` reproduces the
   full setup with skills in every tool.
5. **Fallback verified:** with `skillshare` absent (or PATH-hidden),
   `./bootstrap.sh` deploys all 27 skills via the physical-dir copy path, and
   `~/.claude/skills` contains real directories (no broken symlink).
6. **Ordering verified:** on a clean run, `~/.claude/skills` exists before any
   tool symlink is created; `~/.antigravity/skills` resolves to it.
7. **External skill verified:** `skillshare install github.com/runkids/ai-hooks-integration`
   passes audit, lands in `.skillshare/skills/ai-hooks-integration` as a tracked
   skill, is committed, and appears in targets after `skillshare sync`. No hook
   is wired (deferred).
8. `git status` is clean of unintended deletions; existing tests
   (`bats tests/bats/`, `pytest tests/python/`) still pass.
