# SkillClaw Integration — Design Spec

**Date**: 2026-06-07
**Status**: Approved (design), rev. 2 — review feedback incorporated; pending implementation plan
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
| Capture scope | **Shell-invoked CLI agents only** — Claude Code, Codex, Gemini CLI, cursor-agent CLI. GUI Cursor is **out of scope** (see §5.1). |
| Capture mechanism | **Runtime wrapper functions** (per-invocation health check), **not** a shell-init env export (see §5) |
| Integration depth | **Full managed service** — bootstrap toggle, lib routine, services.yml, health-check, docs |
| Pipeline model | **Approach B** — capture always-on (cheap); evolve + PR on-demand (deliberate, costly) |
| Evolve mode | **workflow** (fixed pipeline — deterministic, cheaper) for the first integration |
| Evolve compute | **Local-model-first** (Ollama/MLX via OpenAI-compatible endpoint); cloud as fallback (see §8) |
| Storage backend | **Local FS** (`~/.skillclaw/`, `chmod 700`) for now; S3/OSS shared storage is a future extension (YAGNI) |
| Capture durability | **Lossy by design** — best-effort tee, never blocks the response path (see §5.2) |
| Default toggle state | **Disabled** — opt-in via `./bootstrap.sh --enable-skillclaw` (critical-path blast radius) |

### Out of scope (YAGNI for this iteration)

- **GUI Cursor (IDE) session capture** — the IDE process does not source the shell rc, so
  runtime wrappers can't reach it; capturing it would require app-level base-URL config or a
  system-wide proxy (much larger blast radius). CLI agents only.
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
- **Env wiring** — fail-open runtime wrapper functions that redirect a CLI agent only when
  the daemon is healthy, checked at invocation time.

---

## 3. File Layout

### New files

| Path | Purpose |
|------|---------|
| `bootstrap/lib/skillclaw.sh` | New lib module (split-by-concern like `mcp.sh`/`auth.sh`): install SkillClaw, run non-interactive `skillclaw setup`, `chmod 700` storage, write runtime wrapper functions, start the supervised daemon. Loaded via `modules.sh`. |
| `configs/claude/config/skillclaw.yml` | Provider, model, storage path (`~/.skillclaw`, local FS), evolve mode (`workflow`), proxy port, staging dir, promotion settings (branch prefix, PR labels). |
| `configs/claude/scripts/skillclaw_promote.sh` | The bridge: evolve → diff → `verify` → branch → `git_ops.sh pr-create`. |
| `.skillshare/skills/skill-evolve/SKILL.md` | `/skill-evolve` slash command — thin wrapper that invokes the promote script and reports the PR. |
| `tests/bats/skillclaw.bats` | Toggle parsing, services.yml write, fail-open runtime wrappers, storage `chmod 700`, promote idempotency + dry-run (mocked). |
| `tests/python/test_skillclaw_promote.py` | Diff classification, frontmatter validation, candidate-drop-on-verify-fail, PR-payload shape. |

### Modified files

| Path | Change |
|------|--------|
| `bootstrap/lib/config.sh` | Add `--enable/--disable-skillclaw` (default **disabled**), `SKILLCLAW_SET` tracking, services.yml read/write. |
| `configs/claude/config/services.yml` | New `skillclaw:` entry (enabled, command, description, proxy port, storage). |
| `.skillshare/skills/health-check/SKILL.md` | Daemon-up + port-listening + `/health` + wrappers-sane + storage-perms checks. |
| `.skillshare/skills/sync-configs/SKILL.md` | Cover `skillclaw.yml` drift + staging dir. |
| `CLAUDE.md`, `.claude/CLAUDE.md`, `docs/` | Document the toggle, the evolve→PR loop, and the kill switch. SkillClaw is a *proposer*; the source of truth stays git-reviewed. |

**Default disabled** because routing all agents through the proxy is opt-in by nature;
enabled with `./bootstrap.sh --enable-skillclaw`.

---

## 4. The Promotion Bridge — `scripts/skillclaw_promote.sh`

The only piece that touches the repo. Pure transform *evolved library → review PR*.
Idempotent; **dry-run by default** (matching `branch-clean` / `version_pin` conventions).

```
skillclaw_promote.sh [--apply] [--skill NAME] [--no-evolve] [--force-new]

0. Idempotency : if an open `skillclaw/evolve-*` PR already exists → ABORT with its URL
                 and tell the user to review/merge it first  (override: --force-new).
                 [Option A — never branch off an unmerged machine-authored proposal.]
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
- **One open evolve-PR at a time** (Option A, step 0) — aborts rather than stacking
  unreviewed machine output on an unmerged proposal.
- **`verify` gate before PR** — an evolved skill that fails validation never reaches
  review (logged, not silently dropped).
- **Provenance in the PR body** — source sessions + SkillClaw version history, so review
  is informed.
- **Never force-push, never touch `main`**, never write outside the staging branch.

---

## 5. Fail-Open Env Wiring (Tier-1 Reliability)

**Risk:** captured agents point at `localhost:<port>`; daemon down → every session breaks.
The daemon sits in the critical path of every captured session.

**Mitigation — runtime wrappers, fail open, never fail closed.**

`bootstrap/lib/skillclaw.sh` writes **wrapper functions** (sourced from shell profile),
**not** a hard env export and **not** a per-shell-init network probe. The health check
runs **at invocation time**, immediately before exec — zero added latency on terminal
open, and the check is always fresh:

```sh
# Defined once in the profile; the probe runs only when you actually invoke an agent.
_skillclaw_base() {
    # 300ms cap so a hung daemon never stalls the agent launch
    curl -sf --max-time 0.3 "http://localhost:${SKILLCLAW_PORT}/health" >/dev/null 2>&1
}
claude() {
    if [ -z "$SKILLCLAW_BYPASS" ] && _skillclaw_base; then
        ANTHROPIC_BASE_URL="http://localhost:${SKILLCLAW_PORT}" command claude "$@"
    else
        command claude "$@"   # daemon down / bypassed → straight to provider, unchanged
    fi
}
# codex() / gemini() / cursor-agent() follow the same shape (OPENAI_BASE_URL for OpenAI-compatible).
```

- **Why wrappers, not shell-init export:** a synchronous `curl` on every shell init adds
  latency to every new terminal and risks a hang. Runtime wrappers move the probe to the
  one moment it matters and cost nothing otherwise.
- **One-flag kill switch**: `./bootstrap.sh --disable-skillclaw` removes the wrappers +
  stops the daemon. `export SKILLCLAW_BYPASS=1` disables redirect for a single shell.
- **`health-check` coverage**: daemon process, port listening, `/health` 200, wrappers
  present-and-correct, evolved-lib writable + `chmod 700`.

### 5.1 Capture-mechanism boundary (CLI only)

Wrapper functions live in the shell. They reach **shell-invoked CLI agents**
(`claude`, `codex`, `gemini`, `cursor-agent`) and nothing else. **GUI Cursor (the IDE)
never sources the shell rc**, so it is **explicitly out of scope** — capturing it would
need app-level base-URL config or a system-wide proxy (a much larger blast radius we are
deliberately not taking on). This is documented, not worked around.

### 5.2 TLS / base-URL compatibility

Redirecting agents from `https://api.anthropic.com` to `http://localhost:<port>` is the
standard local-LLM-proxy pattern (LiteLLM et al.), and the Anthropic + OpenAI SDKs accept
http localhost base URLs — so the CLI case is expected to work **without TLS**.

- **Plan step:** explicitly verify each CLI agent's SDK accepts an `http://localhost` base
  URL during implementation.
- **Fallback only if a specific SDK rejects http:** have the SkillClaw proxy terminate
  local TLS with a self-signed cert + trust-store entry. **Not a default** — only if
  verification proves a hard requirement.

### 5.3 Daemon-crash capture semantics (lossy by design)

Capture is a **best-effort side-effect, never a participant in the request**:

- The proxy **streams provider→agent first** and **tees to capture asynchronously**
  (write-behind). A capture or disk error is **swallowed** — the agent receives its full
  response and never knows. We never `graceful-close + retry` to protect a capture (that
  risks re-running an expensive completion for no user benefit).
- A **daemon crash mid-stream** drops that one in-flight session. We **accept the loss**
  rather than engineer delivery guarantees — guaranteeing capture would put it back in the
  critical path, defeating the fail-open design. Evolution is statistical over many
  sessions; one loss is noise.
- **Self-healing:** a process supervisor (`launchd KeepAlive` / `systemd
  Restart=on-failure`) restarts the daemon; the runtime wrapper routes the *next*
  invocation direct-to-provider while it's still down.
- Only a genuine **provider** error propagates to the agent (its normal retry logic
  handles it). A capture/daemon fault **never** does.

---

## 6. Capture Storage Security (Tier-1)

Intercepting raw `/v1/*` traffic turns `~/.skillclaw/` into a honeypot of session tokens,
proprietary code, and any secrets pasted into prompts.

- **`chmod 700 ~/.skillclaw/`** enforced by `bootstrap/lib/skillclaw.sh` at setup — V1,
  non-negotiable.
- **Secret scrubbing:** first verify whether SkillClaw redacts at capture. **If it does
  not, a regex scrubber is a V1 gate** (not future work) — strip `Authorization`/`x-api-key`
  headers and `sk-…` / `anthropic-…` / bearer-token patterns from the payload **before** it
  is written to disk. Capturing raw auth headers unredacted across all CLI agents is an
  unacceptable liability given the all-agents scope.
- **Never commit captured data:** `~/.skillclaw/` is outside the repo; ensure any in-repo
  staging dir used by the promote bridge is `.gitignore`-covered except the final
  `SKILL.md` artifacts.

---

## 7. Testing & Docs

- **bats** (`tests/bats/skillclaw.bats`): `--enable/--disable` parsing, `SKILLCLAW_SET`
  precedence, services.yml round-trip, wrappers emit **runtime-guarded** redirect (probe
  capped at 0.3s, honors `SKILLCLAW_BYPASS`, falls back to `command <agent>` when daemon
  down), `chmod 700` on storage, promote idempotency abort on open PR, promote dry-run
  prints diff and makes **zero** git mutations.
- **pytest** (`tests/python/test_skillclaw_promote.py`): NEW/CHANGED/UNCHANGED
  classification, frontmatter validation, candidate-drop-on-verify-fail, PR-payload
  shape — mocked SkillClaw lib + mocked `git_ops.sh`.
- **shellcheck / yamllint** clean on new shell + yml.
- **Docs**: toggle + evolve loop + kill switch in `CLAUDE.md`, `.claude/CLAUDE.md`
  (skillshare section — SkillClaw is a *proposer*; source of truth stays git-reviewed),
  and a short `docs/` section.

---

## 8. Evolve Compute — Local-Model-First

The evolution step (sessions → refined `SKILL.md`) is asynchronous, batch-heavy, and off
the user's critical path — ideal for **local compute**.

- **Default:** point SkillClaw's evolve provider at a **local model** (Ollama or MLX,
  exposed via their OpenAI-compatible endpoint), configured in `skillclaw.yml`. Keeps the
  pipeline self-contained, sidesteps rate limits, and zeroes out API cost for background
  evolution.
- **Fallback:** a cloud model (existing Anthropic creds + a cheap tier, e.g. Haiku) when no
  local runtime is present — also configurable in `skillclaw.yml`.
- **Quality tradeoff, and why it's safe here:** small local models author lower-quality
  skills. Because **every** evolved skill is PR-gated and `verify`-checked, lower quality
  only means *more rejected PRs* — never a poisoned library. The quality risk is fully
  absorbed by the gate, so local-first carries no correctness downside.

### Open detail (confirm during planning, non-blocking)

- Exact local model + the cloud fallback tier to name as defaults in `skillclaw.yml`.

---

## 9. Success Criteria

1. `./bootstrap.sh --enable-skillclaw` installs SkillClaw, configures it
   non-interactively, writes the runtime wrapper functions, `chmod 700`s storage, and
   starts the supervised daemon.
2. With the daemon **down**, every wrapped CLI agent still reaches its provider directly,
   with no measurable launch delay (fail-open + no-init-latency verified by test).
3. `/skill-evolve` (or `skillclaw_promote.sh --apply`) produces a review PR into
   `.skillshare/skills/` with per-skill commits, provenance, and only `verify`-passing
   candidates — and **aborts** (Option A) if an open `skillclaw/evolve-*` PR exists.
4. Dry-run makes zero git mutations.
5. Captured payloads are stored under `chmod 700`, and (if SkillClaw lacks built-in
   redaction) auth headers / `sk-`-style secrets are scrubbed before write — verified by test.
6. A daemon crash mid-session never corrupts the agent's response; the supervisor restarts
   it and the next invocation routes direct-to-provider while down.
7. `./bootstrap.sh --disable-skillclaw` fully reverts capture (wrappers removed, daemon
   stopped).
8. `health-check` and `sync-configs` report SkillClaw state accurately.
9. All bats + pytest pass; shellcheck + yamllint clean.
