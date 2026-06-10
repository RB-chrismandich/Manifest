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

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME = "~/.skillclaw"
MAX_RUNS = 50
RUNNING, DONE, FAILED, STALE = "running", "done", "failed", "stale"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _write_atomic(path: Path, data: str) -> None:
    """Write via a unique .tmp sibling + os.replace so concurrent readers never
    see a torn file and two writers never collide on the same tmp name."""
    tmp = path.parent / ("%s.%d.tmp" % (path.name, os.getpid()))
    try:
        tmp.write_text(data, encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


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
        return (eta_s, "~%dm left (est)" % max(1, round(eta_s / 60)))
    except (TypeError, ValueError):
        return (None, "estimating…")
