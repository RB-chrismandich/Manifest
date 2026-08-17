"""Auxiliary recovery, audit, and owned-file records for delegate jobs."""

import contextlib
import json
import os
import stat
import tempfile

from .jobstore_files import _atomic_write_0600, _fsync_directory


class JobArtifactsMixin:
    """Manage durable sidecar records owned by one job directory."""

    @staticmethod
    def _validate_recovery(document):
        allowed = {
            "recovery_id",
            "next_tier",
            "next_index",
            "requires_task_resubmission",
        }
        if not isinstance(document, dict) or set(document) != allowed:
            raise ValueError("fallback recovery record has an invalid schema")
        if not all(
            isinstance(document[key], str) and document[key]
            for key in ("recovery_id", "next_tier")
        ):
            raise ValueError("fallback recovery identity must be non-empty")
        if not isinstance(document["next_index"], int) or document["next_index"] < 1:
            raise ValueError("fallback recovery index must be positive")
        if document["requires_task_resubmission"] is not True:
            raise ValueError("fallback recovery must require task resubmission")
        return document

    def write_recovery(self, job_id, document):
        """Persist task-free fallback recovery metadata beside the job record."""
        self._validate_recovery(document)
        path = os.path.join(self.job_dir(job_id), "recovery.json")
        _atomic_write_0600(path, json.dumps(document, sort_keys=True) + "\n")
        return document

    def read_recovery(self, job_id):
        path = os.path.join(self.job_dir(job_id), "recovery.json")
        with open(path, encoding="utf-8") as stream:
            document = json.load(stream)
        return self._validate_recovery(document)

    def clear_recovery(self, job_id):
        path = os.path.join(self.job_dir(job_id), "recovery.json")
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)

    def write_dispatch_unknown_audit(self, job_id, document):
        """Persist an immutable non-resumable launch audit outside record CAS."""
        allowed = {"attempt_id", "recovery_id", "reason", "resumable"}
        if (
            not isinstance(document, dict)
            or set(document) != allowed
            or document.get("resumable") is not False
            or not isinstance(document.get("reason"), str)
            or not document["reason"]
        ):
            raise ValueError("dispatch-unknown audit has an invalid schema")
        path = os.path.join(self.job_dir(job_id), "dispatch-unknown.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as stream:
                current = json.load(stream)
            if current != document:
                raise ValueError("dispatch-unknown audit is immutable")
            return current
        _atomic_write_0600(path, json.dumps(document, sort_keys=True) + "\n")
        _fsync_directory(self.job_dir(job_id))
        return document

    def has_dispatch_unknown_audit(self, job_id):
        return os.path.isfile(
            os.path.join(self.job_dir(job_id), "dispatch-unknown.json")
        )

    @staticmethod
    def _validate_launch_exclusion(document):
        allowed = {
            "attempt_id",
            "process_start_identity",
            "recovery_id",
            "resumable",
        }
        if (
            not isinstance(document, dict)
            or set(document) != allowed
            or not isinstance(document.get("attempt_id"), str)
            or not document["attempt_id"]
            or not isinstance(document.get("process_start_identity"), str)
            or not document["process_start_identity"]
            or (
                document.get("recovery_id") is not None
                and (
                    not isinstance(document["recovery_id"], str)
                    or not document["recovery_id"]
                )
            )
            or document.get("resumable") is not False
        ):
            raise ValueError("launch exclusion has an invalid schema")
        return document

    def write_launch_exclusion(self, job_id, document):
        """Persist the non-resumable boundary before any worker can exist."""
        self._validate_launch_exclusion(document)
        path = os.path.join(self.job_dir(job_id), "launch-exclusion.json")
        _atomic_write_0600(path, json.dumps(document, sort_keys=True) + "\n")
        _fsync_directory(self.job_dir(job_id))
        return document

    def read_launch_exclusion(self, job_id):
        path = os.path.join(self.job_dir(job_id), "launch-exclusion.json")
        with open(path, encoding="utf-8") as stream:
            return self._validate_launch_exclusion(json.load(stream))

    def has_launch_exclusion(self, job_id):
        return os.path.isfile(
            os.path.join(self.job_dir(job_id), "launch-exclusion.json")
        )

    def clear_launch_exclusion(self, job_id, expected):
        """Retire only the exact exclusion whose launch outcome was proven."""
        path = os.path.join(self.job_dir(job_id), "launch-exclusion.json")
        current = self.read_launch_exclusion(job_id)
        if current != self._validate_launch_exclusion(expected):
            raise ValueError("launch exclusion identity changed")
        os.unlink(path)
        _fsync_directory(self.job_dir(job_id))

    def replace_owned_file(self, job_id, name, content=""):
        """Atomically replace one regular file confined to its private job dir."""
        if name not in {"output.txt", "job.log"}:
            raise ValueError("job file is not coordinator-owned")
        job_dir = os.path.realpath(self.job_dir(job_id))
        path = os.path.join(job_dir, name)
        if os.path.dirname(os.path.realpath(path)) != job_dir:
            raise ValueError("job output path escaped its private directory")
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            info = None
        if info is not None:
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ValueError("job output path is not a safe regular file")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ValueError("job output path is not a safe regular file")
            finally:
                os.close(descriptor)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=job_dir)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
            _fsync_directory(job_dir)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
