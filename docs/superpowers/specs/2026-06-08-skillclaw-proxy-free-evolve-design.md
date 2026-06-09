# SkillClaw Proxy-Free Evolve — Design

> Replace SkillClaw's inline capture proxy with passive transcript ingestion,
> keeping the PR-gated skill-evolution value while severing the Max-incompatible
> man-in-the-middle.

**Date**: 2026-06-08
**Status**: Approved (design) — pending implementation plan
**Supersedes capture half of**: `2026-06-07-skillclaw-integration-design.md`
**Audience**: Manifest maintainers

---

## Problem

The SkillClaw integration shipped in
[`2026-06-07-skillclaw-integration-design.md`](2026-06-07-skillclaw-integration-design.md)
captures CLI-agent sessions through a local proxy (`ANTHROPIC_BASE_URL` /
`OPENAI_BASE_URL` → `127.0.0.1`). On a **Claude Max subscription** this is
fundamentally broken:

- **Symptom (confirmed):** routing `claude` through the proxy breaks the Max
  OAuth flow. The fail-open wrapper therefore bypasses the proxy on every
  invocation.
- **Evidence from the live install** (`~/.skillclaw/`):
  - `dashboard.db` → `sessions: 0`. **Zero sessions have ever been captured.**
  - `config.yaml` shows the proxy configured for OAuth (`api_key: oauth`,
    `claw_type: claude`, `proxy.port: 30000`) yet still produces nothing.
  - The installed tool stores evolved skills in `dashboard.db` (SQLite), but
    Manifest's `skillclaw_promote.sh` reads `~/.skillclaw/skills/<name>/SKILL.md`
    — a **schema mismatch** that would prevent promotion even if capture worked.
  - `retrieval_mode: template, top_k: 6` — the proxy also does runtime skill
    *injection*, which is **redundant**: Claude Code already discovers and loads
    skills natively.

Net: a daemon, a launchd supervisor, shell wrappers, and an OAuth-incompatible
proxy are maintained to deliver **zero value**.

## Goal

Preserve the one genuinely valuable function — *distill reusable `SKILL.md`
skills from how the user actually works* — while removing the inline proxy
entirely. Reuse the existing, working scrub + classify + PR-gating machinery.

## Non-Goals

- Runtime skill retrieval/injection (Claude Code does this natively).
- Capturing non-Claude CLIs that don't persist transcripts (future extension via
  hooks; see Follow-ups).
- Real-time / streaming capture. Evolution is statistical and on-demand.

---

## Decisions (resolved during brainstorming)

| Decision | Choice |
|----------|--------|
| Capture mechanism | **Passive transcript ingestion** (Approach B) — no proxy |
| Scope | **Retire the proxy entirely** (both `claude` and `codex`) |
| Evolve engine | **`claude -p` headless via Max** — no API key, no proxy, flat-rate, high quality |
| Transcript scope | **All projects, last 30 days** (configurable `window_days`); rely on scrub |
| Trigger | On-demand via existing `/skill-evolve` (dry-run default, `--apply` opens PR) |

## Architecture & data flow

```text
~/.claude/projects/**/*.jsonl        (Claude Code transcripts, already on disk)
        │
        ▼
 skillclaw_ingest.py    parse JSONL → normalized session records;
        │               filter to window_days; incremental via state file
        ▼
 skillclaw_scrub.py     REUSED — redact secrets / API keys / auth headers
        │
        ▼
 skillclaw_evolve.py    batch scrubbed sessions → distillation prompt →
        │               `claude -p` → write SKILL.md candidates to
        │               ~/.skillclaw/skills/<name>/SKILL.md
        ▼
 skillclaw_promote.sh   REUSED — classify NEW/CHANGED vs committed library,
        │               validate frontmatter, PR-gate (one open PR at a time)
        ▼
   review PR → .skillshare/skills/   (human merge = source of truth)
```

No socket. No request-path interception. Runs only when invoked.

## Components

### New

- **`configs/claude/scripts/skillclaw_ingest.py`**
  - Reads `~/.claude/projects/**/*.jsonl` (path configurable).
  - Normalizes each session: user prompts, assistant reasoning, and tool
    **names + arguments**. Emits one JSON file per session into
    `~/.skillclaw/sessions/`.
  - **Aggressive stripping (noise reduction).** Transcripts are dominated by
    artifacts — base64 screenshots, full file reads, multi-thousand-line diffs.
    Ingest retains the user prompt, the assistant's reasoning, and tool
    names/args, but **truncates raw tool `stdout`/`stderr` payloads beyond
    `max_tool_output_chars` (default 500)** and drops binary/base64 blobs
    outright. This is the primary token-control lever and runs with zero LLM
    cost.
  - **Window filter:** drop sessions older than `window_days` (default 30) by
    transcript mtime / session timestamp.
  - **Freshness / settle threshold (concurrency safety).** Claude Code streams
    to these `.jsonl` files live. Ingest **skips any file whose mtime is newer
    than `settle_minutes` (default 5)** so it never reads a half-written session,
    and **parses line-by-line, tolerating a trailing partial/malformed line**
    (skip, don't crash).
  - **Incremental:** a state file (`~/.skillclaw/.ingest-state.json`) records
    processed session IDs + mtimes; re-runs only ingest new/changed transcripts.

- **`configs/claude/scripts/skillclaw_evolve.py`**
  - Replaces the dead `skillclaw evolve --mode workflow` binary call.
  - Bundles scrubbed sessions + the current committed skill library into a
    distillation prompt; invokes `claude -p` (headless print mode, Max-backed).
  - **Map-reduce chunking (context-window safety).** Estimates the scrubbed
    payload's token count. If it exceeds `token_budget` (default ~100k), it
    splits sessions into N chunks, runs one `claude -p` distillation per chunk
    (the *map* — each emits candidate skills), then runs a final *reduce* pass
    that merges/dedupes candidates across chunks. Below budget, it's a single
    pass. This keeps each prompt well clear of the 200k limit and preserves the
    model's ability to spot discrete reusable patterns.
  - Writes/refreshes `SKILL.md` candidates to `~/.skillclaw/skills/<name>/`.
  - Output is validated downstream by `skillclaw_promote.py` (frontmatter check).
    **Rejected candidates are surfaced, not dropped silently** — see below.

- **`configs/claude/prompts/skillclaw_evolve.md`** — the distillation prompt
  template `skillclaw_evolve.py` fills with scrubbed sessions + the current
  library. Deployed to `~/.claude/prompts/`. Keeps the "intelligence" reviewable
  and version-controlled rather than buried in a Python string.

### Reused unchanged

- `skillclaw_scrub.py` — secret redaction.
- `skillclaw_promote.py` — classify NEW/CHANGED/UNCHANGED + frontmatter validation.
  Already returns a `dropped[]` list with reasons; **extended** so each rejected
  candidate's `SKILL.md` is copied to `~/.skillclaw/skills/rejected/<name>/` for
  inspection rather than discarded.
- `skillclaw_promote.sh` — PR gating (Option A: one open `skillclaw/evolve-*` PR),
  per-skill commits, dry-run default. **Two changes:** (1) swap the
  `skillclaw evolve` invocation (lines ~69–73) for `skillclaw_evolve.py`;
  (2) when `dropped[]` is non-empty, emit a distinct, prominent warning even if
  the promote list is empty — e.g. `"Generated N candidate(s), but M failed
  schema validation. See ~/.skillclaw/skills/rejected/"` — so a generation
  failure never reads as "no new skills found."

### Removed

- `bootstrap/lib/skillclaw.sh`: proxy setup, daemon lifecycle, crash supervisor,
  launchd/systemd unit, and the shell-profile `claude()` / `codex()` wrappers.
- The upstream `skillclaw` pip dependency.
- `proxy:` and `capture:` blocks in `skillclaw.yml`.
- `--enable-skillclaw` is redefined: "enable transcript-based skill evolution"
  (no daemon to start; just deploys the scripts + config).

## Config rewrite (`configs/claude/config/skillclaw.yml`)

```yaml
storage:
  root: ~/.skillclaw
  sessions: ~/.skillclaw/sessions
  evolved: ~/.skillclaw/skills
  rejected: ~/.skillclaw/skills/rejected   # candidates that failed validation
  state: ~/.skillclaw/.ingest-state.json

ingest:
  transcripts_dir: ~/.claude/projects
  window_days: 30              # all projects, recent window
  settle_minutes: 5           # skip files whose mtime is newer (still being written)
  max_tool_output_chars: 500  # truncate raw tool stdout/stderr beyond this; drop base64
  # allowlist: []             # optional future: restrict to project paths

evolve:
  engine: claude-cli          # `claude -p` headless, Max-backed
  token_budget: 100000        # map-reduce chunk threshold; stays clear of 200k limit
  # model: <optional override; default = CLI default>
  prompt_template: ~/.claude/prompts/skillclaw_evolve.md   # distillation prompt

promotion:
  branch_prefix: skillclaw/evolve-
  pr_base: main
  pr_labels: [needs-review, follow-up]
```

## Migration & teardown

1. **Stop & remove the proxy stack:** `skillclaw_daemon stop`; `launchctl unload`
   + delete `~/Library/LaunchAgents/com.manifest.skillclaw.plist`; reuse
   `skillclaw_remove_wrappers` to strip the managed `claude()`/`codex()` block
   from the shell profile.
2. **Drop the dependency:** uninstall the `skillclaw` pip package (optional;
   leaving it installed is harmless once unused).
3. `--disable-skillclaw` already removes wrappers and stops the daemon; extend it
   to also unload the launchd unit for a full revert.
4. Deploy the two new scripts + the evolve prompt template + rewritten
   `skillclaw.yml` via `bootstrap.sh`.
5. **Annexation.** Once the pip package and proxy daemon are gone, "SkillClaw" is
   no longer an external tool — it is **a set of Manifest-owned Python scripts**,
   and `~/.skillclaw/` is **solely managed by this repo's scripts**. The upstream
   tool's legacy artifacts (`~/.skillclaw/config.yaml`, `dashboard.db`,
   `backups/`) become vestigial: bootstrap leaves them in place (harmless) but
   nothing reads them. Document this ownership shift in `docs/SKILLCLAW.md` so the
   `~/.skillclaw/config.yaml` (upstream schema) is not confused with the
   Manifest-owned `~/.claude/config/skillclaw.yml`.

## Testing

- **pytest `test_skillclaw_ingest.py`:** JSONL parsing of representative
  transcripts; `window_days` filtering; incremental state (re-run ingests nothing
  new); malformed/partial-trailing-line tolerance (skip, don't crash);
  **tool-output truncation** beyond `max_tool_output_chars` + base64 drop;
  **settle threshold** (a file with mtime < `settle_minutes` is skipped).
- **pytest `test_skillclaw_evolve.py`:** prompt assembly from scrubbed sessions;
  `claude -p` invocation mocked (no network); output written only when
  frontmatter-valid; empty-session input → no candidates, clean exit;
  **map-reduce path** (payload > `token_budget` → multiple mapped calls + one
  reduce; merge/dedupe of cross-chunk candidates).
- **pytest `test_skillclaw_promote.py` (extended):** rejected candidate is copied
  to `~/.skillclaw/skills/rejected/<name>/` and reported in `dropped[]`.
- **Reused green:** `test_skillclaw_scrub.py`.
- **bats:** update the promote case that asserted the `skillclaw evolve` call to
  assert the `skillclaw_evolve.py` call; add a case asserting the **validation-
  failure warning** prints even when the promote list is empty; keep dry-run /
  PR-gating cases.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Transcripts from unrelated repos leak into prompts | `skillclaw_scrub.py` redacts secrets; `window_days` bounds volume; `allowlist` is a one-line future tightening |
| `claude -p` unavailable / not logged in | Evolve exits non-zero with a clear message; pipeline is dry-run-safe and opens no PR |
| Claude transcript JSONL format drift | Ingest is defensive (skip unparseable records, tolerate partial trailing line); covered by pytest fixtures |
| Context-window exhaustion (30d × all projects > 200k) | Heuristic stripping in ingest (tool-output truncation) + map-reduce chunking in evolve at `token_budget` |
| Distillation drowns in transcript noise (diffs, base64, file reads) | `max_tool_output_chars` truncation + base64 drop at ingest; only prompts/reasoning/tool-args survive |
| Reading a half-written live session | `settle_minutes` mtime threshold + line-by-line parse skipping the trailing partial object |
| Generation failure misread as "nothing found" | Rejected candidates written to `rejected/` with a prominent warning distinct from "Nothing to promote" |

## Follow-ups (not in V1)

- **Hook-based capture** (`SessionEnd`/`Stop`) for CLIs that don't persist
  transcripts (codex, gemini, cursor-agent). Redundant for Claude.
- **Scheduled evolution** via launchd/cron — trivial now that it's just a script.
- **Project allowlist** for stricter scoping.
- **Tiered engine** (local Ollama → `claude -p` fallback) if offline/cost-private
  runs become desirable.

---

## Related Documents

- [2026-06-07 SkillClaw Integration (original)](2026-06-07-skillclaw-integration-design.md)
- [docs/SKILLCLAW.md](../../SKILLCLAW.md)
- [/skill-evolve skill](../../../.skillshare/skills/skill-evolve/SKILL.md)
