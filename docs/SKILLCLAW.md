# SkillClaw Integration

> PR-gated skill evolution from Claude Code transcripts — no proxy, no daemon

**Last Updated**: 2026-06-08
**Audience**: Operators, developers
**Prerequisites**: Manifest installed (`./bootstrap.sh`)

SkillClaw distills reusable `SKILL.md` skills from your Claude Code session transcripts
and proposes them as pull requests. It is a **PR-gated proposer**: nothing reaches the
committed `.skillshare/skills/` library without a merged PR.

SkillClaw is a set of Manifest-owned scripts. `~/.skillclaw/` is solely managed by
this repo. The legacy upstream `~/.skillclaw/config.yaml` and `dashboard.db` are
vestigial (left in place, never read) and must not be confused with the
Manifest-owned config at `~/.claude/config/skillclaw.yml`.

## Enable / disable

```bash
./bootstrap.sh --enable-skillclaw    # create chmod-700 storage; remove any legacy proxy install
./bootstrap.sh --disable-skillclaw   # storage left intact; nothing running
```

Enabling SkillClaw only sets up storage and tears down any legacy proxy install left
by a prior version. There is no daemon, no socket, and no shell wrapper to install.

## How capture works (passive)

SkillClaw reads Claude Code's own `~/.claude/projects/**/*.jsonl` transcripts directly.
Nothing sits inline between you and the provider — capture is **purely passive** and
works natively with a Claude Max subscription (no API key required).

Key ingest parameters (from `~/.claude/config/skillclaw.yml`):

- **`window_days: 30`** — only transcripts from the last 30 days are considered.
- **`settle_minutes: 5`** — files whose mtime is newer than 5 minutes are skipped
  to avoid reading sessions that are still being written.
- **`max_tool_output_chars: 500`** — raw tool stdout/stderr (including base64
  blobs) is truncated beyond this to control noise and token consumption.

Incremental state is tracked in `~/.skillclaw/.ingest-state.json` so re-runs
only process new content.

## Evolve engine

Skill candidates are distilled using `claude -p` in headless mode, backed by your
Claude Max subscription (no API key, no OpenAI dependency). A **map-reduce** approach
chunks the session corpus under the `token_budget` threshold (default `100000`) to
stay well clear of the 200 k context limit.

## Promote flow

```bash
~/.claude/scripts/skillclaw_promote.sh             # ingest → scrub → evolve → classify (dry-run)
~/.claude/scripts/skillclaw_promote.sh --no-evolve # classify existing evolved library only (dry-run)
~/.claude/scripts/skillclaw_promote.sh --apply     # open ONE review PR (one commit per skill)
```

Pipeline stages:

1. **Ingest** — reads `~/.claude/projects/**/*.jsonl` into `~/.skillclaw/sessions/`.
2. **Scrub** — `skillclaw_scrub.py` redacts secrets before any content is evolved.
3. **Evolve** — `skillclaw_evolve.py` produces `SKILL.md` candidates in `~/.skillclaw/skills/`.
4. **Classify** — validates candidates; rejected ones are copied to `~/.skillclaw/skills/rejected/`
   with a warning printed to stderr (never silently dropped).
5. **PR gate** — `--apply` stages one branch with one commit per skill and opens a
   single `skillclaw/evolve-*` PR against `main`.

**Option A** (one open PR at a time): if an open `skillclaw/evolve-*` PR already
exists, `--apply` aborts with a message. Review or merge it first, or pass
`--force-new` to override.

`/skill-evolve` is the Claude Code skill entry point for this flow.

## Audit log + live status

Each `skillclaw_promote` run writes two best-effort artifacts under `~/.skillclaw/`
(fail-open — audit I/O never aborts or delays a run):

- **`promote.log`** — append-only JSONL audit history (one event per line:
  `run_start`, `stage_start`/`stage_end`, `chunk_done`, `candidates`, `pr_opened`,
  `run_end`/`run_error`). Self-trims to the most recent ~50 runs.
- **`status.json`** — overwritten snapshot of the current/last run plus a rough,
  explicitly-labeled ETA (only the evolve stage predicts, and only once ≥2 chunks
  complete; before that it shows `estimating…`).

During a run the evolve stage prints a live per-chunk line to stderr, e.g.
`[skillclaw] evolve · chunk 4/12 · 1m00s · ~2m left (est)`.

Query the latest run at any time:

```bash
skillclaw_promote.sh --status
# run 20260609T2305 · evolve · chunk 4/12 · 1m00s elapsed · ~2m left (est)
# last run: done · 3 candidates · PR https://…/pull/7 · 4m12s
# no recent run
```

The log records counts, names, timings, and URLs only — never session content
(evolve inputs are already scrubbed upstream).

## Security

- Storage `~/.skillclaw/` and its subdirectories (`sessions/`, `skills/`) are
  `chmod 700` — set at enable time and re-enforced on each `skillclaw_apply_state` call.
- `skillclaw_scrub.py` redacts API keys and auth headers from ingested sessions
  before any content is passed to the evolve engine.

## Follow-ups (not in V1)

- **Non-Claude CLI capture** — codex, gemini, and cursor do not persist transcripts
  to a known location; hook-based capture would be needed for those CLIs.
- **Scheduled evolution** — run `skillclaw_promote.sh` automatically via launchd or cron.
- **Project allowlist** — restrict ingestion to specific project paths for tighter scoping.
- **Tiered local engine** — optional Ollama-backed evolve stage as a cheaper first pass.

---

## Related Documents

- [Commands Guide](COMMANDS.md) - Full command reference including `/skill-evolve`
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - SkillClaw capture & evolve pipeline diagram
- [Getting Started](GETTING_STARTED.md) - First-time Manifest setup
- [README.md](../README.md) - Project overview and SkillClaw feature summary
