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
if skillshare is installed and `.skillshare/config.yaml` exists:
    run `skillshare sync`        # preferred path
else:
    existing symlink/copy deploy  # unchanged fallback — skills still land
```

- bootstrap **does not hard-require** skillshare and does not auto-install it as
  a blocker. It may *offer* to install it (Homebrew: `brew install skillshare`),
  but a missing skillshare only drops to the fallback with a clear notice.
- bootstrap adds the `~/.antigravity/skills → ~/.claude/skills` symlink to its
  existing per-tool symlink routine (needed by both paths).
- The fallback continues to deploy the same skills (now sourced via the
  `configs/claude/skills` → `.skillshare/skills` symlink), so behavior is
  identical whether or not skillshare is present.

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

## Out of Scope

- skillshare hubs, web UI (`ui`), TUI mode.
- skillshare's native git `push`/`pull` (Manifest git covers it).
- Agent distribution.
- Migrating away from `bootstrap.sh` (it stays; skillshare slots into it).

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| skillshare doesn't follow the `configs/claude/skills` symlink when reading source | Source is `.skillshare/skills/` (real dir); the symlink is only for backward-compat *consumers*, not skillshare's source. No risk to skillshare. |
| `cp -r configs/claude/*` in bootstrap follows the symlink and double-deploys skills | bootstrap's skill deploy is gated: `skillshare sync` when present, else the existing symlink deploy — never both (§4). |
| Copilot/Antigravity real skills-dir path unknown | Verify against each tool's docs before wiring; project default `.github/skills` is the known-good fallback for Copilot. |
| `config.yaml` re-managed by skillshare and re-added to `.gitignore` on upgrade | Note in repo docs; re-check `.skillshare/.gitignore` after `skillshare upgrade`. |
| Fresh machine lacks `skillshare` binary | Non-blocking: bootstrap drops to the symlink fallback and deploys skills anyway; skillshare stays optional. |
| Pre-1.0 tool (v0.19, single maintainer) breaks or changes behavior | skillshare is an enhancement layer, not load-bearing; the fallback deploy keeps machines working independent of skillshare. |

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
   `./bootstrap.sh` still deploys all 27 skills via the symlink path.
6. `git status` is clean of unintended deletions; existing tests
   (`bats tests/bats/`, `pytest tests/python/`) still pass.
