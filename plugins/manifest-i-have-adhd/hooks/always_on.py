#!/usr/bin/env python3
"""Fail-open SessionStart delivery for the pinned ADHD guidance."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import signal
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAX_STDIN = 1024 * 1024
STDIN_TIMEOUT_SECONDS = 5
MAX_DEPTH = 32
MAX_STRING = 64 * 1024
MAX_RECORDS = 100
MAX_DIAGNOSTIC_FIELD = 512
MAX_DIAGNOSTIC_TOTAL = 4096
PLUGIN = "manifest-i-have-adhd"
VERSION = "0.1.1"
ALLOWED_REASONS = frozenset(
    {
        "invalid-event",
        "invalid-json",
        "invalid-payload",
        "missing-guidance",
        "runtime-error",
        "timeout",
    }
)


@dataclass(frozen=True)
class HookDiagnostic:
    plugin: str
    version: str
    harness: str
    reason: str

    def __post_init__(self) -> None:
        if self.plugin != PLUGIN or self.version != VERSION:
            raise ValueError("diagnostic identity is not trusted")
        if self.harness not in {"native", "claude", "codex"}:
            raise ValueError("diagnostic harness is not trusted")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError("diagnostic reason is not allowlisted")
        encoded = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        if (
            any(
                len(value.encode("utf-8")) > MAX_DIAGNOSTIC_FIELD
                for value in asdict(self).values()
            )
            or len(encoded) > MAX_DIAGNOSTIC_TOTAL
        ):
            raise ValueError("diagnostic exceeds bounded output limits")

    @classmethod
    def from_error(cls, error: Exception) -> HookDiagnostic:
        """Map an exception to a stable code without retaining its value."""
        reason = str(error) if isinstance(error, RuntimeError) else "runtime-error"
        if reason not in ALLOWED_REASONS:
            reason = "runtime-error"
        return cls(PLUGIN, VERSION, "native", reason)


def _bounded(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("payload nesting exceeds limit")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_STRING:
            raise ValueError("payload string exceeds limit")
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("payload keys must be strings")
            _bounded(key, depth + 1)
            _bounded(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _bounded(child, depth + 1)
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("payload contains an unsupported value")


def _read_stdin() -> bytes:
    """Read the hook payload under a hard deadline.

    A blocking read is the one failure this module's fail-open machinery
    cannot reach: if the write end is never closed, nothing below ever runs
    and the user's session stalls. SIGALRM turns that hang into an ordinary
    exception that main() already handles. Restores any prior handler so the
    hook never leaves a global signal side effect behind.
    """

    def _timed_out(signum, frame):
        del signum, frame
        # Distinct from invalid-payload: a hanging harness and malformed input
        # are different operational problems and must not share a diagnostic.
        raise RuntimeError("timeout")

    try:
        previous = signal.signal(signal.SIGALRM, _timed_out)
    except ValueError:
        # Not on the main thread; a deadline is unavailable but reading is
        # still correct in the ordinary case.
        return sys.stdin.buffer.read(MAX_STDIN + 1)
    signal.alarm(STDIN_TIMEOUT_SECONDS)
    try:
        return sys.stdin.buffer.read(MAX_STDIN + 1)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _payload() -> dict[str, Any]:
    raw = _read_stdin()
    if len(raw) > MAX_STDIN:
        raise ValueError("payload exceeds limit")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid-json") from error
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    _bounded(value)
    if value.get("hook_event_name") != "SessionStart":
        raise RuntimeError("invalid-event")
    for field in ("session_id", "cwd", "source"):
        if field in value and not isinstance(value[field], str):
            raise ValueError(f"{field} must be a string")
    return value


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_root() -> Path:
    configured = os.environ.get("MANIFEST_STATE_ROOT")
    if configured:
        return Path(configured)
    return (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "manifest"
    )


def render_instructions(skill_path: Path | None = None) -> str:
    path = skill_path or _root() / "guidance" / "always-on.md"
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise ValueError("guidance frontmatter is unterminated")
        text = text[end + 5 :]
    if not text.strip():
        raise ValueError("guidance is empty")
    return text.rstrip()


def record_hook_failure(state_root: Path, diagnostic: HookDiagnostic) -> None:
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_root / "diagnostics" / "manifest-i-have-adhd.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_suffix(".lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        records = _load_existing_records(path)
        record = asdict(diagnostic)
        records = [item for item in records if item != record]
        records.append(record)
        payload = (
            json.dumps(records[-MAX_RECORDS:], sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _load_existing_records(path: Path) -> list[dict[str, str]]:
    """Retain only bounded rows that pass the current trusted diagnostic schema."""
    if not path.exists() or path.is_symlink() or not path.is_file():
        return []
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            raw = stream.read(MAX_DIAGNOSTIC_TOTAL + 1)
        if len(raw) > MAX_DIAGNOSTIC_TOTAL:
            return []
        decoded = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list) or len(decoded) > MAX_RECORDS:
        return []
    retained: list[dict[str, str]] = []
    for row in decoded:
        if not isinstance(row, dict):
            continue
        try:
            trusted = HookDiagnostic(**row)
        except (TypeError, ValueError):
            continue
        retained.append(asdict(trusted))
    return retained


def main() -> int:
    reason = "runtime-error"
    try:
        _payload()  # Values are validated but never rendered into model-visible output.
        sys.stdout.write(
            f"Manifest ADHD guidance v{VERSION}\n\n{render_instructions()}\n"
        )
        return 0
    except RuntimeError as error:
        if str(error) in ALLOWED_REASONS:
            reason = str(error)
    except (OSError, UnicodeError):
        reason = "missing-guidance"
    except (TypeError, ValueError):
        reason = "invalid-payload"
    # constitution: exempt C-ERR -- this hook runs on every session and its whole
    # contract is fail-open. An enumerated whitelist makes that promise only as
    # good as the list: an AttributeError from a harness that hands us a stdin
    # without .buffer would escape and break the session with a traceback. The
    # specific reason is still classified above; this only guarantees exit 0.
    except Exception:
        reason = "runtime-error"
    with contextlib.suppress(Exception):
        # Harness identity is trusted bundle metadata, not SessionStart input.
        record_hook_failure(
            _state_root(), HookDiagnostic(PLUGIN, VERSION, "native", reason)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
