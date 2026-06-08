# SkillClaw Integration — Design Spec

**Date**: 2026-06-07
**Status**: Approved (design) — pending implementation plan
**Author**: Claude Code (brainstorming session with @ReefBytes-Owner)
**Topic**: Integrate [SkillClaw](https://github.com/AMAP-ML/SkillClaw) to auto-evolve Manifest's `SKILL.md` library from real agent session data, gated behind PR review.

---

## 1. Goal & Scope

Use **SkillClaw** as an automatic skill author/refiner whose output flows back into
Manifest's committed source of truth (`.skillshare/skills/`) **only through a reviewed PR**.

SkillClaw is a Python 3.10+ system with two parts:

- **Client proxy** — a local daemon that intercepts LLM API traffic
  (`/v1/chat/completions`, `/v1/messages`) to capture session data and maintain a
  local evolved-skill library.
- **Evolve server / pipeline** — processes captured sessions into improved `SKILL.md`
  files (dedupe, refine, validate), using a fixed-LLM **workflow** mode or an
  **agent** mode, over shared storage (local FS, OSS, or S3).

### Decisions locked in this session

| Decision | Choice |
|----------|--------|
| Primary outcome | **Auto-evolve our skills** — feed refinements back into `.skillshare/skills/` |
| Promotion gate | **PR-gated review** — nothing enters the source of truth without a merged PR |
| Capture scope | **All OpenAI-compatible agents** (Claude Code, Codex, Cursor, Gemini where possible) |
| Integration depth | **Full managed service** — bootstrap toggle, lib routine, services.yml, health-check, docs |
| Pipeline model | **Approach B** — capture always-on (cheap); evolve + PR on-demand (deliberate, costly) |
| Evolve mode | **workflow** (fixed pipeline — deterministic, cheaper) for the first integration |
| Storage backend | **Local FS** (`~/.skillclaw/`) for now; S3/OSS shared storage is a future extension (YAGNI) |
| Default toggle state | **Disabled** — opt-in via `./bootstrap.sh --enable-skillclaw` (critical-path blast radius) |

### Out of scope (YAGNI for this iteration)

- Shared team storage (S3/OSS) and cross-device sync.
- SkillClaw `agent`-mode evolution.
- Always-on background evolve server.
- Auto-merge of evolved skills (review is always human).

---

## 2. Architecture & Data Flow

```
┌─ Capture (always-on, cheap) ──────────────────────────────┐
│  agents (claude / codex / cursor / gemini)                 │
│      │  base-URL env → http://localhost:<port>             │
│      ▼                                                     │
│  skillclaw proxy daemon  ──► session store + evolved lib   │
│                                  ~/.skillclaw/             │
└────────────────────────────────────────────────────────────┘
                                   │
        you trigger /skill-evolve  │  (on-demand, costly)
                                   ▼
┌─ Evolve + Promote (deliberate, reviewable) ───────────────┐
│  skillclaw evolve (workflow mode)  ──► staged SKILL.md     │
│      ▼                                                     │
│  scripts/skillclaw_promote.sh                              │
│   1. diff staged vs .skillshare/skills/                    │
│   2. run `verify` skill on each candidate                  │
│   3. git branch + git_ops.sh pr-create  ──► review PR      │
└────────────────────────────────────────────────────────────┘
                                   │ you merge
                                   ▼
                    .skillshare/skills/  (source of truth)
                                   │ bootstrap.sh deploy_home_skills
                                   ▼
            ~/.claude/skills + Cursor/Gemini/Codex/Antigravity
```

**Invariant:** data flows *one way into* the source of truth, and only through a PR.
SkillClaw never writes to `.skillshare/skills/` directly.

### Component boundaries (each independently testable)

- **Install/config** — gets SkillClaw onto the box + non-interactive `skillclaw setup`.
  Knows nothing about promotion.
- **Capture daemon** — SkillClaw's own proxy; Manifest only starts/stops/health-checks it.
- **Promotion bridge** — pure transform *evolved library → review PR*. No always-on
  state; reuses `git_ops.sh` + the `verify` skill.
- **Env wiring** — fail-open shim that only redirects agents when the daemon is healthy.

---

## 3. File Layout

### New files

| Path | Purpose |
|------|---------|
| `bootstrap/lib/skillclaw.sh` | New lib module (split-by-concern like `mcp.sh`/`auth.sh`): install SkillClaw, run non-interactive `skillclaw setup`, write env shim, start daemon. Loaded via `modules.sh`. |
| `configs/claude/config/skillclaw.yml` | Provider, model, storage path (`~/.skillclaw`, local FS), evolve mode (`workflow`), proxy port, staging dir, promotion settings (branch prefix, PR labels). |
| `configs/claude/scripts/skillclaw_promote.sh` | The bridge: evolve → diff → `verify` → branch → `git_ops.sh pr-create`. |
| `.skillshare/skills/skill-evolve/SKILL.md` | `/skill-evolve` slash command — thin wrapper that invokes the promote script and reports the PR. |
| `tests/bats/skillclaw.bats` | Toggle parsing, services.yml write, fail-open env shim, promote dry-run (mocked). |
| `tests/python/test_skillclaw_promote.py` | Diff classification, frontmatter validation, candidate-drop-on-verify-fail, PR-payload shape. |

### Modified files

| Path | Change |
|------|--------|
| `bootstrap/lib/config.sh` | Add `--enable/--disable-skillclaw` (default **disabled**), `SKILLCLAW_SET` tracking, services.yml read/write. |
| `configs/claude/config/services.yml` | New `skillclaw:` entry (enabled, command, description, proxy port, storage). |
| `.skillshare/skills/health-check/SKILL.md` | Daemon-up + port-listening + `/health` + env-shim-sane checks. |
| `.skillshare/skills/sync-configs/SKILL.md` | Cover `skillclaw.yml` drift + staging dir. |
| `CLAUDE.md`, `.claude/CLAUDE.md`, `docs/` | Document the toggle, the evolve→PR loop, and the kill switch. SkillClaw is a *proposer*; the source of truth stays git-reviewed. |

**Default disabled** because routing all agents through the proxy is opt-in by nature;
enabled with `./bootstrap.sh --enable-skillclaw`.

---

## 4. The Promotion Bridge — `scripts/skillclaw_promote.sh`

The only piece that touches the repo. Pure transform *evolved library → review PR*.
Idempotent; **dry-run by default** (matching `branch-clean` / `version_pin` conventions).

```
skillclaw_promote.sh [--apply] [--skill NAME] [--no-evolve]

1. Preflight   : daemon healthy? evolved lib exists? git clean? on a branch?
2. Evolve      : `skillclaw evolve --mode workflow`   (skip with --no-evolve)
3. Diff        : compare ~/.skillclaw/skills/*/SKILL.md  vs  .skillshare/skills/*/SKILL.md
                 → classify each: NEW | CHANGED | UNCHANGED(skip)
4. Validate    : per candidate — frontmatter (name+description) lint + run `verify` skill;
                 drop any that fail, log why (NO silent drops)
5. Stage       : copy survivors into a fresh branch  skillclaw/evolve-<n-skills>
6. PR          : git_ops.sh pr-create  (title lists skills, body = per-skill diff +
                 SkillClaw provenance: source sessions, version history)
7. Report      : print PR URL  (or, in dry-run, the diff table + what *would* PR)
```

### Design decisions baked in

- **Dry-run default** — `--apply` required to actually branch+PR. The diff table prints first.
- **One PR per evolution batch, one commit per skill** — granular review; drop an
  individual skill by reverting its commit.
- **`verify` gate before PR** — an evolved skill that fails validation never reaches
  review (logged, not silently dropped).
- **Provenance in the PR body** — source sessions + SkillClaw version history, so review
  is informed.
- **Never force-push, never touch `main`**, never write outside the staging branch.

---

## 5. Fail-Open Env Wiring (Tier-1 Reliability)

**Risk:** all agents pointed at `localhost:<port>`; daemon down → every session breaks.
The daemon sits in the critical path of every captured session.

**Mitigation — fail open, never fail closed:**

- `bootstrap/lib/skillclaw.sh` writes a **guarded shim** (sourced from shell profile),
  not a hard env export:

  ```sh
  # only redirect if the SkillClaw daemon is actually answering
  if curl -sf -m 1 "http://localhost:${SKILLCLAW_PORT}/health" >/dev/null 2>&1; then
      export ANTHROPIC_BASE_URL="http://localhost:${SKILLCLAW_PORT}"
      export OPENAI_BASE_URL="http://localhost:${SKILLCLAW_PORT}/v1"
  fi   # else: agents talk to providers directly, unchanged
  ```

- **One-flag kill switch**: `./bootstrap.sh --disable-skillclaw` removes the shim +
  stops the daemon. `export SKILLCLAW_BYPASS=1` disables redirect for a single shell
  instantly.
- **`health-check` coverage**: daemon process, port listening, `/health` 200, shim
  present-and-correct, evolved-lib writable.
- The shim re-checks health **per shell init**, so a dead daemon degrades to
  direct-to-provider rather than failing.

---

## 6. Testing & Docs

- **bats** (`tests/bats/skillclaw.bats`): `--enable/--disable` parsing, `SKILLCLAW_SET`
  precedence, services.yml round-trip, shim emits **guarded** (not hard) export, promote
  dry-run prints diff and makes **zero** git mutations.
- **pytest** (`tests/python/test_skillclaw_promote.py`): NEW/CHANGED/UNCHANGED
  classification, frontmatter validation, candidate-drop-on-verify-fail, PR-payload
  shape — mocked SkillClaw lib + mocked `git_ops.sh`.
- **shellcheck / yamllint** clean on new shell + yml.
- **Docs**: toggle + evolve loop + kill switch in `CLAUDE.md`, `.claude/CLAUDE.md`
  (skillshare section — SkillClaw is a *proposer*; source of truth stays git-reviewed),
  and a short `docs/` section.

---

## 7. Open Detail (confirm during planning, non-blocking)

- **Evolve provider/model** SkillClaw uses for the evolution step — defaults to existing
  Anthropic credentials + a cheap model (e.g. Haiku), configurable in `skillclaw.yml`.

---

## 8. Success Criteria

1. `./bootstrap.sh --enable-skillclaw` installs SkillClaw, configures it
   non-interactively, writes the guarded shim, and starts the daemon.
2. With the daemon **down**, all agents still reach their providers directly (fail-open
   verified by test).
3. `/skill-evolve` (or `skillclaw_promote.sh --apply`) produces a review PR into
   `.skillshare/skills/` with per-skill commits, provenance, and only `verify`-passing
   candidates.
4. Dry-run makes zero git mutations.
5. `./bootstrap.sh --disable-skillclaw` fully reverts capture (shim removed, daemon
   stopped).
6. `health-check` and `sync-configs` report SkillClaw state accurately.
7. All bats + pytest pass; shellcheck + yamllint clean.
