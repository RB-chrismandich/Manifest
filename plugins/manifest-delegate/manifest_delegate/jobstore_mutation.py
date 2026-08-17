"""CAS-locked delegate job-record mutation and fallback resolution."""

import fcntl
import json
import os
import stat
import tempfile
import time

from . import constants
from .jobstore_states import TERMINAL_STATES


class JobMutationMixin:
    """Read and mutate record.json under its per-job flock."""

    def _lock_path(self, job_id):
        return os.path.join(self.job_dir(job_id), ".lock")

    def read(self, job_id):
        record_path = os.path.join(self.job_dir(job_id), "record.json")
        with open(record_path, encoding="utf-8") as fh:
            return json.load(fh)

    def read_locked(self, job_id):
        """Read one coherent record while holding its mutation lock."""
        lock_fd = os.open(self._lock_path(job_id), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            with open(
                os.path.join(self.job_dir(job_id), "record.json"), encoding="utf-8"
            ) as stream:
                return json.load(stream)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def reject_fallback(self, job_id, *, expected_version, recovery_id, action):
        """Resolve task-free recovery without validating a backend or payload."""
        if action not in {"reject", "cancel"}:
            raise ValueError("invalid fallback rejection action")
        current = self.read_locked(job_id)
        audit = current.get("recovery_audit")
        if current.get("state") == "fallback_rejected":
            if (
                isinstance(audit, dict)
                and audit.get("recovery_id") == recovery_id
                and audit.get("action") == action
            ):
                return current
            raise ValueError(
                "fallback recovery already resolved by a conflicting action"
            )
        if current.get("state") != "fallback_pending":
            raise ValueError("job is not fallback_pending")
        if current.get("version") != expected_version:
            raise ValueError(
                "stale job version: expected {}, found {}".format(
                    expected_version, current.get("version")
                )
            )
        recovery = current.get("recovery")
        try:
            stored = self.read_recovery(job_id)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("fallback recovery identity is invalid") from error
        if (
            not isinstance(recovery, dict)
            or recovery != stored
            or recovery.get("recovery_id") != recovery_id
        ):
            raise ValueError("fallback recovery identity does not match")

        def _reject(record):
            if record.get("state") != "fallback_pending":
                return None
            record["state"] = "fallback_rejected"
            record["fallback_pending"] = False
            record["recovery_audit"] = {
                "action": action,
                "recovery_id": recovery_id,
                "resolved_from_version": expected_version,
            }
            record.pop("recovery", None)
            record.pop("worker_pid", None)
            record.pop("worker_pgid", None)
            record.pop("worker_start_identity", None)
            record.pop("foreground", None)
            record.pop("dispatch", None)
            return record

        resolved = self.mutate(job_id, _reject, expected_version=expected_version)
        self.clear_recovery(job_id)
        return resolved

    def mutate(self, job_id, mutator, expected_version=None):
        """Compare-and-replace mutation inside a per-job flock.

        `mutator(record) -> record | None`. Returning None means "refuse the
        mutation" (e.g. record is already terminal); the caller gets back the
        current on-disk record unchanged.
        """
        job_dir = self.job_dir(job_id)
        lock_path = self._lock_path(job_id)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            record_path = os.path.join(job_dir, "record.json")
            with open(record_path, encoding="utf-8") as fh:
                current = json.load(fh)
            if (
                expected_version is not None
                and current.get("version") != expected_version
            ):
                raise ValueError(
                    "stale job version: expected {}, found {}".format(
                        expected_version, current.get("version")
                    )
                )
            if (
                current.get("state") in TERMINAL_STATES
                and mutator.__name__ != "_reaper_noop"
            ):
                # Terminal states are immutable; refuse silently (no-op).
                allow_terminal = getattr(mutator, "allow_terminal_reentry", False)
                if not allow_terminal:
                    return current
            updated = mutator(current)
            if updated is None:
                return current
            updated["updated_at"] = time.time()
            updated["version"] = current.get("version", 1) + 1
            fd, tmp_path = tempfile.mkstemp(
                dir=job_dir, prefix=".record.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(updated, indent=2))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
                os.replace(tmp_path, record_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError as cleanup_exc:
                    constants.err(
                        f"job {job_id}: failed to remove stale tempfile {tmp_path}: {cleanup_exc}"
                    )
                raise
            return updated
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
