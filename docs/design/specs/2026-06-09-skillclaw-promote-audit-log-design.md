# SkillClaw Promote — Audit Log + Live Status/ETA — Design

> A structured, persistent audit record for `skillclaw_promote` runs, plus live
> run status and a rough "time remaining" estimate — surfaced both in the
> terminal and via an on-demand `--status` query.

**Date**: 2026-06-09
**Status**: Approved (design) — pending implementation plan
**Audience**: Manifest maintainers
**Reviewed by**: `agy` (Antigravity CLI) independent design review — 7 findings
(4 important, 3 minor) verified and incorporated: stateless ETA via cumulative
`elapsed_s`, stale-`running` finalization (trap + pid-liveness), per-run status
reset (no state bleed), atomic `trim`, `compute_eta` bounds guards, storage
auto-init, and `${SCRIPT_DIR}`-relative invocation.

---

## Problem

`skillclaw_promote` runs the proxy-free SkillClaw pipeline (ingest → scrub →
evolve → classify → promote). Today it has **no persistent run/audit log** — only
ephemeral stdout and the git/PR provenance of whatever it promotes. The pipeline
is long-running: the **evolve** stage is a map-reduce where each chunk is one
`claude -p` call (seconds to tens of seconds), and `promote.sh` suppresses all
sub-stage output (`>/dev/null`), so during a multi-minute evolve the operator
sees a silent terminal with no sense of progress or how much longer it will take.

We want: (1) a durable, structured **audit record** of each run, and (2) live
**status + a rough ETA** that answers "where is it / how much longer," both as it
runs and on demand.

## Decisions (resolved during brainstorming)

| Decision | Choice |
|----------|--------|
| Artifact structure | **Two artifacts** — append-only `promote.log` (JSONL audit history) + overwritten `status.json` (live current-run snapshot). `--status` is an O(1) read, not a tail-scan. |
| Status surface | **Both** — live progress lines in the terminal during the run, **and** a queryable `skillclaw_promote.sh --status` reading `status.json`. |
| ETA model | **Progress always + rough ETA once measurable.** Show stage + chunk i/N + elapsed always; once ≥2 chunks complete, also show `~Nm left (est)`. Before that, `estimating…`. |
| Retention | `promote.log` self-trims to the most recent **~50 runs**. |
| Query surface | `--status` only (no `--history` in V1). |
| Failure posture | **Fail-open** — audit logging never aborts or delays a promote run. |

## Non-Goals

- No external log shipping / metrics backend (local files only).
- No precise/guaranteed ETA — `claude -p` per-chunk time is variable; the ETA is
  an explicitly-labeled estimate.
- No `--history` browser of past runs (the JSONL is greppable; a viewer is a
  future add).
- No change to what the pipeline *does* — this is observability only.

---

## Architecture

```text
skillclaw_promote.sh ──┐  stage transitions (ingest/scrub/evolve/classify/promote),
                       │  final summary, --status query, mints run_id
                       ├──►  skillclaw_audit.py  ──►  ~/.skillclaw/promote.log  (append-only JSONL: audit history)
skillclaw_evolve.py  ──┘  per-chunk: i/N + seconds        │              ~/.skillclaw/status.json   (overwritten: live snapshot + ETA)
```

`skillclaw_audit.py` is the single source of truth for both file formats; both
the shell orchestrator and the Python evolver write through it.

## Components

### New

- **`configs/claude/scripts/skillclaw_audit.py`** — the logger + status engine.
  - `log(run_id, stage, event, **fields)` — append one JSONL line to
    `~/.skillclaw/promote.log` **and** update `~/.skillclaw/status.json`. A
    `run_start` event — or any event whose `run_id` differs from the one currently
    in `status.json` — **initializes a fresh status structure instead of merging**,
    so a new run can never inherit the prior run's `pr_url`, totals, or evolve
    metrics (no state bleed). All other events merge into the current run's snapshot.
  - `compute_eta(chunks_done, chunks_total, elapsed_s) -> (eta_s|None, label)` —
    returns `(None, "estimating…")` when inputs are insufficient or invalid
    (`chunks_done < 2`, `chunks_total <= chunks_done`, or any non-positive), else
    `((total-done)*elapsed/done, "~Nm left (est)")`. The guards prevent
    negative/div-by-zero ETAs from corrupt or out-of-order status.
  - `render_status() -> str` — human one-glance summary for `--status`
    (running / done / failed / none). **Liveness:** if `state=="running"` but the
    pid embedded in `run_id` is no longer alive, render as `stale` — a crash or
    Ctrl-C that skipped finalization must never show as a phantom running run.
  - `trim(max_runs=50)` — keep only events for the most recent `max_runs`
    `run_id`s in `promote.log`. **Atomic:** writes filtered lines to
    `promote.log.tmp` then `os.replace()` over `promote.log`, so an interrupt or
    full disk during trim can't corrupt or lose the audit history.
  - **Storage init:** ensures `~/.skillclaw/` exists (`mkdir -p` + `chmod 700`)
    before writing, so a fresh install with no dir doesn't silently log nothing.
  - **Fail-open:** every public function wraps its I/O so an error (unwritable
    dir, full disk, malformed status) is swallowed and returns cleanly — it can
    never raise into the pipeline.
  - CLI entry, **always invoked as `python3 "${SCRIPT_DIR}/skillclaw_audit.py"
    <cmd>`** from promote.sh (matching the repo's `${SCRIPT_DIR}/skillclaw_*.py`
    convention — never bare on `PATH`): `log …`, `status`, `trim`.
  - `status.json` and `promote.log` written `chmod 600`; `status.json` via `.tmp`
    + atomic rename (safe concurrent reads under `~/.skillclaw/`, already `700`).

### Modified

- **`configs/claude/scripts/skillclaw_promote.sh`**
  - Mint a `run_id` at start (UTC timestamp + short pid suffix, e.g.
    `20260609T230501Z-4821`).
  - Log `run_start` (config: window_days, token_budget, apply?), `stage_start` /
    `stage_end` for each stage with counts + seconds, `candidates`
    (NEW/CHANGED/DROPPED names + reasons), `pr_opened` (url), and `run_end`
    (state, total_seconds) — or `run_error` (stage, message) on failure.
  - Print a short progress line at each stage transition
    (`▸ evolve (12 chunks)…`).
  - Pass `run_id` to `skillclaw_evolve.py`.
  - New **`--status`** flag → `skillclaw_audit.py status` and exit 0.
  - Call `skillclaw_audit.py trim` once per run.
  - **Finalization trap:** install a `trap` on `EXIT`/`INT`/`TERM` that, if the run
    hasn't already logged `run_end`, logs `run_error` (stage = wherever it died)
    and finalizes `status.json` to `failed` — so a crash, Ctrl-C, or `set -e` exit
    never leaves a phantom `running` status. (Complements the
    `render_status` pid-liveness check as belt-and-suspenders.)

- **`configs/claude/scripts/skillclaw_evolve.py`**
  - Accept `--run-id` (and audit path override for tests).
  - In the existing map-reduce loop, after each chunk completes, call the audit
    logger with a `chunk_done` event carrying `i`, `total`, this chunk's
    `chunk_seconds`, **and the cumulative `elapsed_s` since the evolve stage
    started** (so the ETA is computed statelessly from the event itself, not from
    re-deriving cumulative time inside the logger). The logger updates
    `status.json` (stage=evolve, chunk i/N, elapsed, eta) and the evolver prints
    one live progress line to stderr:
    `[skillclaw] evolve · chunk 4/12 · 1m00s · ~2m left (est)`.
  - Time is real wall-clock (`time.monotonic()`), accumulated across chunks; the
    evolver already has the chunk list, so `total` is known up front.

## Artifact schemas

### `~/.skillclaw/promote.log` (append-only JSONL — audit record)

One event per line: `{"ts": <iso8601>, "run_id": <id>, "stage": <name>, "event": <name>, ...fields}`.
Event sequence per run:

```jsonc
{"ts":"…","run_id":"…","stage":"-","event":"run_start","window_days":30,"token_budget":100000,"apply":true}
{"ts":"…","run_id":"…","stage":"ingest","event":"stage_start"}
{"ts":"…","run_id":"…","stage":"ingest","event":"stage_end","ingested":12,"skipped":459,"seconds":3.1}
{"ts":"…","run_id":"…","stage":"evolve","event":"stage_start","chunks":12}
{"ts":"…","run_id":"…","stage":"evolve","event":"chunk_done","i":1,"total":12,"chunk_seconds":14.2,"elapsed_s":14.2}
…
{"ts":"…","run_id":"…","stage":"classify","event":"candidates","new":["a"],"changed":["b"],"dropped":[{"name":"c","reason":"…"}]}
{"ts":"…","run_id":"…","stage":"promote","event":"pr_opened","url":"https://…/pull/NNN"}
{"ts":"…","run_id":"…","stage":"-","event":"run_end","state":"done","total_seconds":252.4}
```

Errors emit `{"event":"run_error","stage":<where>,"message":<short>}`.

### `~/.skillclaw/status.json` (overwritten — live snapshot)

```jsonc
{
  "run_id": "20260609T230501Z-4821",
  "started_at": "…", "updated_at": "…",
  "state": "running",                       // running | done | failed
  "stage": "evolve",
  // eta_s = (total-chunk) * (elapsed_s / chunk) = (12-4) * (60/4) = 120
  "evolve": {"chunk": 4, "total": 12, "elapsed_s": 60, "eta_s": 120, "eta_label": "~2m left (est)"},
  "totals": {"ingested": 12, "candidates": null, "dropped": null},
  "pr_url": null
}
```

## Live UX + `--status`

- **Terminal (live):** per-chunk stderr line from evolve + a short stage line from
  promote. The existing `>/dev/null` on raw sub-stage output stays; only these
  structured lines surface.
- **`skillclaw_promote.sh --status`:** prints a one-glance summary, e.g.
  `run 20260609T2305 · evolve · chunk 4/12 · 1m00s elapsed · ~2m left (est)`, or
  `last run: done · 3 candidates · PR #NNN · 4m12s`, or `no recent run`.

## Error handling & fail-open

Audit logging is observability, never load-bearing. Every `skillclaw_audit.py`
call (from shell or Python) is best-effort: on any error it logs nothing and
returns success to the caller, so a promote run completes even if the log/status
files can't be written. This mirrors the SkillClaw pipeline's existing fail-open
posture (ingest/scrub/evolve already `|| err`/`|| true`).

## Retention

On each run, `skillclaw_audit.py trim` rewrites `promote.log` keeping only events
whose `run_id` is among the most recent ~50. Bounds the file to a few hundred KB
while preserving a meaningful history. `status.json` is a single snapshot
(constant size).

## Testing

- **pytest `test_skillclaw_audit.py`:** `log()` appends a JSONL line and updates
  `status.json`; **`run_start`/changed-`run_id` resets the snapshot** (prior
  `pr_url`/metrics do not bleed in); `compute_eta` (`done<2 → estimating…`;
  `total<=done` or non-positive → `estimating…`; else `(total-done)*elapsed/done`);
  `render_status` (running / done / none / **`stale` when the run_id pid is
  dead**); `trim` keeps only the last N run_ids **and writes atomically** (a
  simulated mid-trim failure leaves the original log intact); **storage init**
  (`mkdir -p` + 700 when the dir is absent); **fail-open** (unwritable path →
  returns cleanly, no raise, pipeline-safe).
- **pytest `test_skillclaw_evolve.py` (extend):** with the injectable runner + a
  temp audit dir, the map-reduce loop emits one `chunk_done` per chunk and
  `status.json` reflects the correct `chunk`/`total`.
- **bats `skillclaw_promote.bats` (extend):** `run_id` minted and present in
  `promote.log`; `--status` renders from a seeded `status.json`; stage events are
  logged; the **finalization trap logs `run_error` + sets `status.json` failed**
  on a simulated mid-run interrupt; an **unwritable audit path does not abort**
  the run (exit 0).
- **shellcheck** clean; `promote.log` lines and `status.json` are valid JSON.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Audit failure breaks a promote run | Fail-open by construction; bats asserts an unwritable path still exits 0 |
| ETA misleads on high per-chunk variance | Labeled `(est)`; suppressed (`estimating…`) until ≥2 chunks; only evolve predicts |
| Log grows unbounded | `trim` to last ~50 runs each run |
| Concurrent reads of `status.json` mid-write | Write to `status.json.tmp` then atomic `mv` (same pattern as spec-review feedback) |
| Crash/Ctrl-C leaves a phantom `running` status | `trap` finalizes status on EXIT/INT/TERM + `render_status` pid-liveness check reports `stale` |
| New run inherits prior run's status fields (state bleed) | `run_start` / changed `run_id` initializes a fresh `status.json`, never merges across runs |
| `trim` rewrite corrupts the log on interrupt | Atomic `promote.log.tmp` + `os.replace()` |
| `compute_eta` produces negative/div-zero on corrupt status | Guards: `done≥2`, `total>done`, all positive — else `estimating…` |
| Secrets leaking into the log | Log records counts/names/timings/URLs only — never session content; evolve inputs are already scrubbed upstream |

## Follow-ups (not in V1)

- `--history` view (one-line summary per recent run from `promote.log`).
- Per-stage ETA for ingest on very large transcript sets (currently treated as
  fast/fixed).
- Optional metrics/OTel export.

---

## Related Documents

- [docs/SKILLCLAW.md](../../SKILLCLAW.md) — the proxy-free pipeline this instruments
- [2026-06-08 SkillClaw proxy-free evolve design](2026-06-08-skillclaw-proxy-free-evolve-design.md)
- [spec-review design](2026-06-08-spec-review-design.md) — shares the atomic
  `.tmp`+`mv` write and fail-open patterns reused here
