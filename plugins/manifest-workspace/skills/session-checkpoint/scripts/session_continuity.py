#!/usr/bin/env python3
"""Session-scoped compaction telemetry and integrity-checked checkpoints."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REMINDER_THRESHOLD = 2
THRESHOLD_ENV = "MANIFEST_COMPACTION_REMINDER_THRESHOLD"
CHECKPOINT_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
_KNOWN_BOUNDARIES = frozenset({"safe", "active", "unknown"})
_CHECKPOINT_FIELDS = {
    "source_session_id": str,
    "original_goal": str,
    "constraints": list,
    "decisions": list,
    "repository": dict,
    "completed_work": list,
    "remaining_work": list,
    "verification_evidence": list,
    "unresolved_uncertainty": list,
    "next_action": str,
    "live_operations": list,
    "continuation_goal": str,
}


class SessionContinuityError(RuntimeError):
    """Base error for failures that must be surfaced to the caller."""


class ConfigurationError(SessionContinuityError):
    """The continuity policy configuration is invalid."""


class PersistenceError(SessionContinuityError):
    """State could not be durably persisted."""


class IntegrityError(SessionContinuityError):
    """A checkpoint failed its integrity check."""


class CheckpointValidationError(SessionContinuityError):
    """A checkpoint omits required continuation evidence."""


@dataclass(frozen=True)
class SessionStatus:
    """A session count, or an explicit unknown telemetry state."""

    telemetry: str
    compaction_count: int | None
    excluded: bool = False


@dataclass(frozen=True)
class HandoffDecision:
    """An advisory decision that never performs the handoff itself."""

    recommend_fresh_session: bool
    reason: str
    checkpoint_path: Path | None = None
    continuation_goal: str | None = None


@dataclass(frozen=True)
class RevalidationReport:
    """Authority changes that must be reconciled before continuation."""

    trusted: bool
    git_changes: tuple[str, ...]
    ownership_changes: tuple[str, ...]
    continuation_goal: str


def reminder_threshold(environ: Mapping[str, str] | None = None) -> int:
    """Return the positive experimental reminder threshold."""

    source = os.environ if environ is None else environ
    raw = source.get(THRESHOLD_ENV)
    if raw is None:
        return DEFAULT_REMINDER_THRESHOLD
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            f"{THRESHOLD_ENV} must be a positive integer"
        ) from error
    if value <= 0 or str(value) != raw.strip():
        raise ConfigurationError(f"{THRESHOLD_ENV} must be a positive integer")
    return value


def _state_home(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    configured = os.environ.get("XDG_STATE_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".local/state"


def _private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
    except OSError as error:
        raise PersistenceError(
            f"unable to prepare private state directory: {error}"
        ) from error


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _atomic_write(path: Path, document: object) -> None:
    _private_directory(path.parent)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json(document) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        raise PersistenceError(f"unable to persist {path}: {error}") from error


def _read_json(
    path: Path,
    error_type: type[SessionContinuityError] = PersistenceError,
    message: str | None = None,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        detail = message or f"unable to read {path}"
        raise error_type(f"{detail}: {error}") from error
    if not isinstance(value, dict):
        detail = message or f"unable to read {path}"
        raise error_type(f"{detail}: expected a JSON object")
    return value


def _validate_session_state(state: Mapping[str, Any], session_id: str) -> None:
    errors: list[str] = []
    schema_version = state.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != STATE_SCHEMA_VERSION
    ):
        errors.append("schema_version is unsupported")
    if state.get("session_id") != session_id:
        errors.append("session_id does not match the requested session")
    count = state.get("compaction_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append("compaction_count must be a non-negative integer")
    for field in ("pending_precompact", "reminded", "deferred"):
        if not isinstance(state.get(field), bool):
            errors.append(f"{field} must be a boolean")
    if errors:
        raise PersistenceError(f"invalid session state: {'; '.join(errors)}")


def _is_child_event(event: Mapping[str, object]) -> bool:
    return bool(event.get("agent_id"))


class SessionContinuityStore:
    """Persist lifecycle-derived state separately for every session."""

    def __init__(self, state_home: Path | None = None) -> None:
        self.root = _state_home(state_home) / "manifest/session-continuity"

    def _path(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string")
        identity = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self.root / f"{identity}.json"

    @contextmanager
    def _locked_state(self, session_id: str) -> Iterator[dict[str, Any]]:
        _private_directory(self.root)
        state_path = self._path(session_id)
        lock_path = state_path.with_suffix(".lock")
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            os.fchmod(descriptor, 0o600)
        except OSError as error:
            raise PersistenceError(f"unable to lock session state: {error}") from error
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if state_path.exists():
                state = _read_json(state_path)
                _validate_session_state(state, session_id)
            else:
                state = {
                    "schema_version": STATE_SCHEMA_VERSION,
                    "session_id": session_id,
                    "compaction_count": 0,
                    "pending_precompact": False,
                    "reminded": False,
                    "deferred": False,
                }
            yield state
            _atomic_write(state_path, state)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def record_claude_event(self, event: Mapping[str, object]) -> SessionStatus:
        """Count only a primary-session PreCompact→compact SessionStart sequence."""

        session_id = event.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Claude lifecycle event requires session_id")
        if _is_child_event(event):
            return SessionStatus("confirmed", 0, excluded=True)

        with self._locked_state(session_id) as state:
            event_name = event.get("hook_event_name")
            if event_name == "PreCompact":
                state["pending_precompact"] = True
            elif event_name == "SessionStart":
                if event.get("source") == "compact" and state["pending_precompact"]:
                    state["compaction_count"] += 1
                state["pending_precompact"] = False
            count = int(state["compaction_count"])
        return SessionStatus("confirmed", count)

    def status(self, session_id: str, harness: str) -> SessionStatus:
        """Return confirmed Claude state or unknown for every other harness."""

        if harness.lower() != "claude":
            return SessionStatus("unknown", None)
        state_path = self._path(session_id)
        if not state_path.exists():
            return SessionStatus("confirmed", 0)
        state = _read_json(state_path)
        _validate_session_state(state, session_id)
        return SessionStatus("confirmed", int(state.get("compaction_count", 0)))

    def defer(self, session_id: str) -> None:
        """Persist explicit suppression of reminders for this session."""

        with self._locked_state(session_id) as state:
            state["deferred"] = True

    def handoff_decision(
        self, session_id: str, boundary: str, checkpoint_path: Path
    ) -> HandoffDecision:
        """Recommend once only at a safe boundary with a valid checkpoint."""

        if boundary not in _KNOWN_BOUNDARIES:
            raise ValueError(f"boundary must be one of {sorted(_KNOWN_BOUNDARIES)}")
        with self._locked_state(session_id) as state:
            if state["deferred"]:
                return HandoffDecision(False, "deferred")
            if state["reminded"]:
                return HandoffDecision(False, "already-reminded")
            if int(state["compaction_count"]) < reminder_threshold():
                return HandoffDecision(False, "below-threshold")
            if boundary != "safe":
                return HandoffDecision(False, f"{boundary}-boundary")
            checkpoint = read_checkpoint(checkpoint_path)
            if checkpoint["source_session_id"] != session_id:
                raise IntegrityError(
                    "checkpoint integrity failed: session identity mismatch"
                )
            state["reminded"] = True
            return HandoffDecision(
                True,
                "threshold-at-safe-boundary",
                checkpoint_path,
                str(checkpoint["continuation_goal"]),
            )


def _validate_checkpoint(checkpoint: Mapping[str, object]) -> None:
    errors: list[str] = []
    for field, expected_type in _CHECKPOINT_FIELDS.items():
        value = checkpoint.get(field)
        if not isinstance(value, expected_type) or (
            expected_type is str and not value.strip()
        ):
            errors.append(f"{field} must be a non-empty {expected_type.__name__}")

    repository = checkpoint.get("repository")
    if isinstance(repository, dict):
        for field in ("path", "branch", "head", "dirty_tree"):
            expected = list if field == "dirty_tree" else str
            if not isinstance(repository.get(field), expected):
                errors.append(f"repository.{field} is required")

    evidence = checkpoint.get("verification_evidence")
    if isinstance(evidence, list):
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or any(
                not isinstance(item.get(field), str) or not item[field]
                for field in ("command", "outcome", "evidence")
            ):
                errors.append(
                    f"verification_evidence[{index}] requires command, outcome, and evidence"
                )

    operations = checkpoint.get("live_operations")
    if isinstance(operations, list):
        for index, item in enumerate(operations):
            if not isinstance(item, dict) or any(
                not isinstance(item.get(field), str) or not item[field]
                for field in ("owner", "handle", "status", "obligation")
            ):
                errors.append(
                    f"live_operations[{index}] requires owner, handle, status, and obligation"
                )
    if errors:
        raise CheckpointValidationError("; ".join(errors))


def write_checkpoint(
    checkpoint: Mapping[str, object], state_home: Path | None = None
) -> Path:
    """Atomically persist a private checkpoint with a content digest."""

    _validate_checkpoint(checkpoint)
    document = dict(checkpoint)
    digest = hashlib.sha256(_canonical_json(document)).hexdigest()
    envelope = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "integrity": {"algorithm": "sha256", "digest": digest},
        "checkpoint": document,
    }
    root = _state_home(state_home) / "manifest/checkpoints"
    session_hash = hashlib.sha256(
        str(checkpoint["source_session_id"]).encode("utf-8")
    ).hexdigest()[:16]
    path = root / f"{session_hash}-{uuid.uuid4().hex}.json"
    _atomic_write(path, envelope)
    return path


def read_checkpoint(path: Path) -> dict[str, Any]:
    """Read a checkpoint only after its structure and digest are verified."""

    envelope = _read_json(
        path, IntegrityError, "checkpoint integrity verification failed"
    )
    checkpoint = envelope.get("checkpoint")
    integrity = envelope.get("integrity")
    if not isinstance(checkpoint, dict) or not isinstance(integrity, dict):
        raise IntegrityError("checkpoint integrity metadata is missing")
    expected = integrity.get("digest")
    actual = hashlib.sha256(_canonical_json(checkpoint)).hexdigest()
    if integrity.get("algorithm") != "sha256" or expected != actual:
        raise IntegrityError("checkpoint integrity verification failed")
    _validate_checkpoint(checkpoint)
    return checkpoint


def revalidate_continuation(
    checkpoint_path: Path,
    current_repository: Mapping[str, object],
    current_live_operations: Sequence[Mapping[str, object]],
) -> RevalidationReport:
    """Report authority changes before checkpoint claims are trusted."""

    checkpoint = read_checkpoint(checkpoint_path)
    recorded_repository = checkpoint["repository"]
    git_changes = tuple(
        key
        for key in ("path", "branch", "head", "dirty_tree")
        if recorded_repository.get(key) != current_repository.get(key)
    )
    recorded_owners = {
        str(operation["handle"]): str(operation["owner"])
        for operation in checkpoint["live_operations"]
    }
    current_owners = {
        str(operation["handle"]): str(operation["owner"])
        for operation in current_live_operations
        if "handle" in operation and "owner" in operation
    }
    ownership_changes = tuple(
        sorted(
            handle
            for handle in recorded_owners.keys() | current_owners.keys()
            if recorded_owners.get(handle) != current_owners.get(handle)
        )
    )
    return RevalidationReport(
        not git_changes and not ownership_changes,
        git_changes,
        ownership_changes,
        str(checkpoint["continuation_goal"]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the adjacent CLI adapter without mixing presentation into policy."""

    from session_continuity_cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
