#!/usr/bin/env python3
"""SkillClaw promote audit log + live status/ETA engine.

Single source of truth for two artifacts under ~/.skillclaw/:
  - promote.log : append-only JSONL audit history (one event per line)
  - status.json : overwritten snapshot of the current/last run + rough ETA

Fail-open by construction: every public function swallows I/O errors and returns
cleanly, so audit logging can never abort or delay a promote run.

CLI (always invoked as `python3 "${SCRIPT_DIR}/skillclaw_audit.py" <cmd>`):
    log <run_id> <stage> <event> [key=value ...]
    status
    trim [--max-runs N]

Env overrides (tests): SKILLCLAW_AUDIT_DIR (default ~/.skillclaw).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_HOME = "~/.skillclaw"
MAX_RUNS = 50
RUNNING, DONE, FAILED, STALE = "running", "done", "failed", "stale"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit_dir() -> Path:
    return Path(os.environ.get("SKILLCLAW_AUDIT_DIR", DEFAULT_HOME)).expanduser()


def _log_path() -> Path:
    return _audit_dir() / "promote.log"


def _status_path() -> Path:
    return _audit_dir() / "status.json"


def _ensure_storage() -> Path:
    """mkdir -p ~/.skillclaw (700) so a fresh install never silently logs nothing."""
    d = _audit_dir()
    d.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(d, 0o700)
    return d


def _write_atomic(path: Path, data: str) -> None:
    """Write via a unique .tmp sibling + os.replace so concurrent readers never
    see a torn file and two writers never collide on the same tmp name."""
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        tmp.write_text(data, encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def _read_status() -> dict:
    try:
        return json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fresh_status(run_id: str) -> dict:
    now = _now_iso()
    return {
        "run_id": run_id,
        "started_at": now,
        "updated_at": now,
        "state": RUNNING,
        "stage": "-",
        "evolve": None,
        "totals": {"ingested": None, "candidates": None, "dropped": None},
        "pr_url": None,
    }


# Mutates `status` in place and returns it (caller passes a dict it does not retain).
def _apply_event(status: dict, stage: str, event: str, fields: dict) -> dict:
    status["updated_at"] = _now_iso()
    if stage and stage != "-":
        status["stage"] = stage
    if event == "run_start":
        cfg = status.setdefault("config", {})
        for k in ("window_days", "token_budget", "apply"):
            if k in fields:
                cfg[k] = fields[k]
    elif event == "stage_start" and stage == "evolve":
        status["evolve"] = {
            "chunk": 0,
            "total": fields.get("chunks", 0),
            "elapsed_s": 0,
            "eta_s": None,
            "eta_label": "estimating…",
        }
    elif event == "stage_end" and "ingested" in fields:
        status["totals"]["ingested"] = fields["ingested"]
    elif event == "chunk_done":
        done, total = fields.get("i", 0), fields.get("total", 0)
        elapsed = fields.get("elapsed_s", 0)
        eta_s, label = compute_eta(done, total, elapsed)
        status["evolve"] = {
            "chunk": done,
            "total": total,
            "elapsed_s": elapsed,
            "eta_s": eta_s,
            "eta_label": label,
        }
    elif event == "candidates":
        new = fields.get("new") or []
        changed = fields.get("changed") or []
        dropped = fields.get("dropped") or []
        status["totals"]["candidates"] = len(new) + len(changed)
        status["totals"]["dropped"] = len(dropped)
    elif event == "pr_opened":
        status["pr_url"] = fields.get("url")
    elif event == "run_end":
        status["state"] = fields.get("state", DONE)
        status["stage"] = "-"
        status["total_seconds"] = fields.get("total_seconds")
    elif event == "run_error":
        status["state"] = FAILED
        status["error_stage"] = stage
        status["message"] = fields.get("message")
    return status


def log(run_id, stage, event, **fields):
    """Append one JSONL audit line and update the live status snapshot. Fail-open."""
    try:
        _ensure_storage()
        line = {"ts": _now_iso(), "run_id": run_id, "stage": stage, "event": event}
        line.update(fields)
        # promote.log is the authoritative record; status.json is best-effort and
        # may lag the log by one event if the process dies between the two writes.
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        with contextlib.suppress(OSError):
            os.chmod(_log_path(), 0o600)
        current = _read_status()
        if event == "run_start" or current.get("run_id") != run_id:
            current = _fresh_status(run_id)
        _write_atomic(
            _status_path(),
            json.dumps(_apply_event(current, stage, event, fields), indent=2),
        )
    except Exception:
        return


def _pid_from_run_id(run_id):
    try:
        return int(str(run_id).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


def _pid_alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    except OSError:
        return False
    return True


def _fmt_secs(s):
    try:
        s = round(float(s))
    except (TypeError, ValueError):
        return "?"
    if s < 0:
        return "?"
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def render_status():
    """One-glance human summary for --status. Fail-open -> 'no recent run'."""
    try:
        st = _read_status()
        if not st:
            return "no recent run"
        state = st.get("state")
        run_id = st.get("run_id", "?")
        short = str(run_id).split("-")[0][:13]
        if state == RUNNING and not _pid_alive(_pid_from_run_id(run_id)):
            state = STALE
        if state == RUNNING:
            ev = st.get("evolve") or {}
            stage = st.get("stage", "?")
            if stage == "evolve" and ev.get("total"):
                return "run {} · evolve · chunk {}/{} · {} elapsed · {}".format(
                    short,
                    ev.get("chunk"),
                    ev.get("total"),
                    _fmt_secs(ev.get("elapsed_s")),
                    ev.get("eta_label", "estimating…"),
                )
            return f"run {short} · {stage} · running"
        if state == STALE:
            return f"run {short} · stale (no live process)"
        if state == FAILED:
            return "last run: failed · stage {}".format(st.get("error_stage", "?"))
        if state == DONE:
            tot = st.get("totals", {})
            parts = ["last run: done"]
            if tot.get("candidates") is not None:
                parts.append("{} candidates".format(tot["candidates"]))
            if st.get("pr_url"):
                parts.append("PR {}".format(st["pr_url"]))
            if st.get("total_seconds") is not None:
                parts.append(_fmt_secs(st["total_seconds"]))
            return " · ".join(parts)
        return "no recent run"
    except Exception:
        return "no recent run"


def trim(max_runs=MAX_RUNS):
    """Keep only events for the most recent max_runs run_ids. Atomic. Fail-open."""
    try:
        # Clamp to >=1 so a non-positive max_runs can never keep all/an unexpected
        # slice via order[-max_runs:] (e.g. -0 == 0 would retain everything).
        try:
            max_runs = max(1, int(max_runs))
        except (TypeError, ValueError):
            max_runs = MAX_RUNS
        path = _log_path()
        if not path.exists():
            return
        order, seen = [], set()
        # ⚡ Bolt: Avoid caching large parsed lists in memory. Two-pass lazy
        # iteration drastically reduces peak memory usage on huge log files.
        with path.open("r", encoding="utf-8") as fd:
            for ln in fd:
                # ⚡ Bolt: Fast-path prefix check to bypass json.loads exception overhead for noise lines
                if not ln or (ln[0] != "{" and ln.lstrip()[:1] != "{"):
                    continue
                try:
                    obj = json.loads(ln)
                    # A valid-JSON non-dict line (torn write leaving `123`/`null`)
                    # raised AttributeError past this handler into the outer
                    # fail-open except, permanently disabling trimming (issue #311)
                    if not isinstance(obj, dict):
                        continue
                    rid = obj.get("run_id")
                except json.JSONDecodeError:
                    continue
                if rid not in seen:
                    seen.add(rid)
                    order.append(rid)
        keep = set(order[-max_runs:])
        kept = []
        # Pass 2: only collect kept lines
        with path.open("r", encoding="utf-8") as fd:
            for ln in fd:
                # ⚡ Bolt: Fast-path prefix check to bypass json.loads exception overhead for noise lines
                if not ln or (ln[0] != "{" and ln.lstrip()[:1] != "{"):
                    continue
                try:
                    obj = json.loads(ln)
                    if isinstance(obj, dict) and obj.get("run_id") in keep:
                        kept.append(ln.rstrip("\n"))
                except json.JSONDecodeError:
                    continue
        _write_atomic(path, "\n".join(kept) + ("\n" if kept else ""))
    except Exception:
        return


def _parse_kv(pairs):
    """Parse `key=value` argv pairs; JSON-decode each value, else keep the string."""
    out = {}
    for p in pairs:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)

        try:
            parsed = json.loads(v)
            if (
                isinstance(parsed, (dict, list, int, float, bool, str))
                or parsed is None
            ):
                out[k] = parsed
            else:
                out[k] = v
        except json.JSONDecodeError:
            out[k] = v
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "status":
        print(render_status())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "trim":
        mx = MAX_RUNS
        if "--max-runs" in rest:
            i = rest.index("--max-runs")
            try:
                mx = int(rest[i + 1])
            except (IndexError, ValueError):
                mx = MAX_RUNS
        trim(mx)
        return 0
    if cmd == "log":
        if len(rest) < 3:
            return 0  # fail-open: a malformed call never errors the pipeline
        log(rest[0], rest[1], rest[2], **_parse_kv(rest[3:]))
        return 0
    return 0  # unknown subcommand: fail-open


def compute_eta(chunks_done, chunks_total, elapsed_s):
    """Return (eta_s|None, label).

    `estimating…` until >=2 chunks are done and inputs are sane; otherwise a
    linear projection. Guards prevent negative/div-by-zero ETAs from corrupt or
    out-of-order status.
    """
    try:
        if chunks_done < 2 or chunks_total <= chunks_done or elapsed_s <= 0:
            return (None, "estimating…")
        eta_s = (chunks_total - chunks_done) * (elapsed_s / chunks_done)
        # Deliberately minute-granular and rough: any sub-minute ETA rounds up to
        # "~1m left (est)" — the label is an explicit estimate, not a countdown.
        return (eta_s, f"~{max(1, round(eta_s / 60))}m left (est)")
    except (TypeError, ValueError):
        return (None, "estimating…")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
