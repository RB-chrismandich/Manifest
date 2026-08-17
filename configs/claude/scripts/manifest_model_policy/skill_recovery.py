"""Private, task-free recovery records for direct skill fallback."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


def _validate_attempts(document: dict[str, object]) -> None:
    tiers = document["remaining_tiers"]
    attempts = document["attempts"]
    if (
        not isinstance(tiers, list)
        or not tiers
        or not all(isinstance(tier, str) and tier for tier in tiers)
        or not isinstance(attempts, list)
        or len(attempts) >= 4
    ):
        raise ValueError("skill-run recovery attempts are invalid")
    for attempt in attempts:
        if (
            not isinstance(attempt, dict)
            or set(attempt) != {"tier", "model"}
            or not isinstance(attempt["tier"], str)
            or not attempt["tier"]
            or (attempt["model"] is not None and not isinstance(attempt["model"], str))
        ):
            raise ValueError("skill-run recovery attempt is invalid")


def _validate_record(document: object) -> dict[str, object]:
    fields = {
        "recovery_id",
        "version",
        "skill_path",
        "harness",
        "remaining_tiers",
        "fallback_mode",
        "attempts",
        "requires_task_resubmission",
        "state",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise ValueError("skill-run recovery has an invalid schema")
    if not isinstance(document["recovery_id"], str):
        raise ValueError("skill-run recovery ID is invalid")
    if not isinstance(document["version"], int) or document["version"] < 1:
        raise ValueError("skill-run recovery version is invalid")
    if not all(
        isinstance(document[name], str) and document[name]
        for name in ("skill_path", "harness", "fallback_mode")
    ):
        raise ValueError("skill-run recovery identity is invalid")
    _validate_attempts(document)
    if document["requires_task_resubmission"] is not True:
        raise ValueError("skill-run recovery must require task resubmission")
    if document["state"] not in {"pending", "claimed"}:
        raise ValueError("skill-run recovery state is invalid")
    return document


def _fsync_directory(path: Path) -> None:
    directory = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _mutable_document(record: dict[str, object], *, state: str) -> dict[str, object]:
    document = {
        key: value
        for key, value in record.items()
        if key not in {"recovery_id", "version"}
    }
    document["state"] = state
    return document


class SkillRecoveryStore:
    """Persist versioned recovery state without retaining task text."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            configured = os.environ.get("MANIFEST_SKILL_RUN_STATE_ROOT")
            if configured:
                root = Path(configured)
            else:
                state = Path(
                    os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")
                )
                root = state / "manifest" / "skill-run-recovery"
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def _path(self, recovery_id: str) -> Path:
        if len(recovery_id) != 32 or any(
            char not in "0123456789abcdef" for char in recovery_id
        ):
            raise ValueError("recovery ID is invalid")
        return self.root / f"{recovery_id}.json"

    def _atomic_write(self, path: Path, document: dict[str, object]) -> None:
        descriptor, name = tempfile.mkstemp(prefix=".recovery-", dir=self.root)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
            _fsync_directory(self.root)
        finally:
            temporary.unlink(missing_ok=True)

    def create(self, document: dict[str, object]) -> dict[str, object]:
        """Create a private pending recovery record at version one."""
        recovery_id = uuid.uuid4().hex
        record = _validate_record(
            {
                **document,
                "state": document.get("state", "pending"),
                "recovery_id": recovery_id,
                "version": 1,
            }
        )
        path = self._path(recovery_id)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            self._atomic_write(path, record)
        # constitution: exempt C-ERR -- remove reserved partial state on any failure.
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return record

    def read(self, recovery_id: str) -> dict[str, object]:
        """Read and validate one recovery without following symlinks."""
        path = self._path(recovery_id)
        if path.is_symlink() or not path.is_file():
            raise ValueError("skill-run recovery does not exist")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            document = json.load(stream)
        record = _validate_record(document)
        if record["recovery_id"] != recovery_id:
            raise ValueError("skill-run recovery identity does not match")
        return record

    def replace(
        self, recovery_id: str, expected_version: int, document: dict[str, object]
    ) -> dict[str, object]:
        """Replace one recovery through a versioned compare-and-swap."""
        path = self._path(recovery_id)
        lock = os.open(path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.read(recovery_id)
            self._require_version(current, expected_version)
            record = _validate_record(
                {
                    **document,
                    "state": document.get("state", current["state"]),
                    "recovery_id": recovery_id,
                    "version": expected_version + 1,
                }
            )
            self._atomic_write(path, record)
            return record
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)

    @staticmethod
    def _require_version(current: dict[str, object], expected_version: int) -> None:
        if current["version"] != expected_version:
            raise ValueError(
                f"stale recovery version: expected {expected_version}, "
                f"found {current['version']}"
            )

    def delete(self, recovery_id: str, expected_version: int) -> None:
        """Delete one recovery only at its expected version."""
        path = self._path(recovery_id)
        lock_path = path.with_suffix(".lock")
        lock = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._require_version(self.read(recovery_id), expected_version)
            path.unlink()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
        lock_path.unlink(missing_ok=True)
        # release_claim only unlocks and closes, so without this every resumed
        # recovery would leave a permanent 0-byte .claim behind in the state
        # directory. A live claimer keeps its open descriptor valid, and the
        # next claim() re-creates the file via O_CREAT.
        path.with_suffix(".claim").unlink(missing_ok=True)

    def claim(
        self, recovery_id: str, expected_version: int
    ) -> tuple[dict[str, object], int]:
        """CAS pending to claimed while holding a crash-released lifetime lock."""
        claim_path = self._path(recovery_id).with_suffix(".claim")
        descriptor = os.open(claim_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("skill-run recovery has an active claim") from error
            current = self.read(recovery_id)
            if current["state"] != "pending":
                raise ValueError("skill-run recovery is already claimed")
            claimed = self.replace(
                recovery_id,
                expected_version,
                _mutable_document(current, state="claimed"),
            )
            return claimed, descriptor
        # constitution: exempt C-ERR -- release lifetime lock on any failure.
        except Exception:
            os.close(descriptor)
            raise

    def recover_abandoned(self, recovery_id: str) -> dict[str, object]:
        """Return a crash-abandoned claim to pending using its lifetime lock."""
        current = self.read(recovery_id)
        if current["state"] != "claimed":
            return current
        descriptor = os.open(
            self._path(recovery_id).with_suffix(".claim"),
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return current
            latest = self.read(recovery_id)
            if latest["state"] != "claimed":
                return latest
            return self.replace(
                recovery_id,
                int(latest["version"]),
                _mutable_document(latest, state="pending"),
            )
        finally:
            os.close(descriptor)

    @contextmanager
    def holding_claim(self, recovery_id: str):
        """Hold this recovery's lifetime claim lock for the whole block.

        claim() takes the .claim flock BEFORE it writes state="claimed" (which
        goes through the separate .lock file), so the on-disk state can still
        read "pending" while a claimant is mid-flight. Probing the lock and
        releasing it would only narrow that window -- a claimant could take the
        flock between the probe and the caller's delete. Holding it across the
        whole mutation closes it: either we own the claim for the duration, or
        a live claimant does and we never touch the record.

        Raises ValueError if a live claimant holds it.
        """
        descriptor = os.open(
            self._path(recovery_id).with_suffix(".claim"),
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("skill-run recovery has an active claim") from error
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @staticmethod
    def release_claim(descriptor: int) -> None:
        """Release a live recovery claim after a terminal transition."""
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
