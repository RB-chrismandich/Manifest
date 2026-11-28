"""Fail-open, redacted telemetry for hook-driven check runs."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime

from manifest_agent.paths import xdg_paths
from manifest_agent.process import redact_text

from .state import acquire_lock_until


def _redact(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _record(
    client: str, profile: str | None, status: str, duration_seconds: float
) -> dict[str, object]:
    return {
        "schema": 1,
        "ts": datetime.now(UTC).isoformat(),
        "profile": profile or "",
        "receipt_key": "",
        "head_sha": "",
        "candidate_lineage": None,
        "attempt": 1,
        "status": status,
        "duration_seconds": duration_seconds,
        "model_id": "unknown",
        "runtime": {"client": client, "version": "unknown"},
        "cost": {"status": "unknown"},
    }


def record_hook_telemetry(
    client: str,
    profile: str | None,
    status: str,
    duration_seconds: float,
    deadline_monotonic: float | None = None,
) -> None:
    """Append one local record; telemetry failure never changes the verdict."""
    try:
        directory = xdg_paths(os.environ).state / "telemetry"
        directory.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(
            directory / ".runs.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            acquire_lock_until(lock_fd, deadline_monotonic)
            payload = json.dumps(
                _redact(_record(client, profile, status, duration_seconds)),
                sort_keys=True,
                separators=(",", ":"),
            )
            flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW
            record_fd = os.open(directory / "runs.jsonl", flags, 0o600)
            try:
                os.write(record_fd, f"{payload}\n".encode())
                os.fsync(record_fd)
            finally:
                os.close(record_fd)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except OSError:
        return
