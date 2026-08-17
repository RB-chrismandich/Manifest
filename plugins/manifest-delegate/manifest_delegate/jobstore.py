"""Durable per-job state for manifest-delegate."""

import fcntl
import json
import os
import time
import uuid

from .jobstore_artifacts import JobArtifactsMixin
from .jobstore_files import (
    _atomic_write_0600 as _atomic_write_0600,
)
from .jobstore_files import (
    _fsync_directory,
)
from .jobstore_files import (
    _mkdir_0700 as _mkdir_0700,
)
from .jobstore_files import (
    _write_0600 as _write_0600,
)
from .jobstore_files import (
    delegations_root as delegations_root,
)
from .jobstore_files import (
    workspace_slug as workspace_slug,
)
from .jobstore_mutation import JobMutationMixin
from .jobstore_prune import JobPruneMixin
from .jobstore_reaper import JobReaperMixin
from .jobstore_states import (
    FALLBACK_PENDING_EXPIRES_AFTER_SECONDS as FALLBACK_PENDING_EXPIRES_AFTER_SECONDS,
)
from .jobstore_states import (
    FALLBACK_PENDING_RESOLUTION_ACTIONS as FALLBACK_PENDING_RESOLUTION_ACTIONS,
)
from .jobstore_states import (
    NON_TERMINAL_STATES as NON_TERMINAL_STATES,
)
from .jobstore_states import (
    RESOLVABLE_STATES as RESOLVABLE_STATES,
)
from .jobstore_states import (
    SETTLED_STATES as SETTLED_STATES,
)
from .jobstore_states import (
    TERMINAL_STATES as TERMINAL_STATES,
)


class JobStore(
    JobArtifactsMixin,
    JobMutationMixin,
    JobReaperMixin,
    JobPruneMixin,
):
    """Per-job record directories with CAS-locked record mutation."""

    def __init__(self, cwd=None, root=None):
        self.workspace_dir = os.path.join(
            root or delegations_root(), workspace_slug(cwd)
        )
        _mkdir_0700(self.workspace_dir)

    def job_dir(self, job_id):
        return os.path.join(self.workspace_dir, job_id)

    def create(self, backend_id, extra=None, *, prune_exclude=None):
        job_id = uuid.uuid4().hex
        job_dir = self.job_dir(job_id)
        _mkdir_0700(job_dir)
        now = time.time()
        record = {
            "job_id": job_id,
            "backend": backend_id,
            "state": "queued",
            "pgid": None,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }
        if extra:
            record.update(extra)
        _write_0600(os.path.join(job_dir, "record.json"), json.dumps(record, indent=2))
        _write_0600(os.path.join(job_dir, "output.txt"), "")
        _write_0600(os.path.join(job_dir, "job.log"), "")
        self._prune(exclude_job_id=prune_exclude)
        return record

    def create_second_opinion(
        self,
        source_job_id,
        backend_id,
        *,
        expected_version,
        attempt_id,
        findings_digest,
        validator,
        extra=None,
    ):
        """Create a bound child while holding the source record's CAS lock."""
        lock_fd = os.open(self._lock_path(source_job_id), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            with open(
                os.path.join(self.job_dir(source_job_id), "record.json"),
                encoding="utf-8",
            ) as stream:
                source = json.load(stream)
            context = validator(source)
            if (
                context.get("version") != expected_version
                or context.get("attempt_id") != attempt_id
                or context.get("findings_digest") != findings_digest
            ):
                raise ValueError("second-opinion source changed concurrently")
            child_extra = dict(extra or {})
            child_extra.update(
                {
                    "second_opinion_of": source_job_id,
                    "second_opinion_source_version": expected_version,
                    "second_opinion_attempt_id": attempt_id,
                    "second_opinion_findings_digest": findings_digest,
                }
            )
            child = self.create(
                backend_id, extra=child_extra, prune_exclude=source_job_id
            )
            _fsync_directory(self.workspace_dir)
            return child
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
