"""Retention pruning for terminal delegate job directories."""

import fcntl
import logging
import os

from . import constants
from .jobstore_states import TERMINAL_STATES


class JobPruneMixin:
    """List jobs and prune the oldest resolved terminal records."""

    def list_job_ids(self):
        if not os.path.isdir(self.workspace_dir):
            return []
        return [
            name
            for name in os.listdir(self.workspace_dir)
            if os.path.isdir(os.path.join(self.workspace_dir, name))
        ]

    def _prune(self, exclude_job_id=None):
        """Delete oldest resolved terminal jobs beyond KEEP_LAST_N.

        Queued, running, and unresolved fallback-pending jobs are never prune
        candidates and never count toward the KEEP_LAST_N cap, regardless of
        age. Pending jobs resolve only through approve/reject/cancel or an
        explicit versioned approve/reject/cancel action. There is deliberately
        no time-based expiration because task resubmission is operator-driven.

        ``exclude_job_id`` names a job whose ``.lock`` the caller already holds
        open. flock is per open file description, so ``_delete_job_locked``
        re-opening that same lock file would block on the caller's own lock and
        deadlock the process; excluding it also keeps a second-opinion parent
        from being deleted while its child is being bound to it.
        """
        job_ids = self.list_job_ids()
        entries = []
        for job_id in job_ids:
            if exclude_job_id is not None and job_id == exclude_job_id:
                continue
            try:
                record = self.read(job_id)
            except (OSError, ValueError):
                continue
            if record.get("state") not in TERMINAL_STATES:
                continue
            record_path = os.path.join(self.job_dir(job_id), "record.json")
            try:
                mtime = os.path.getmtime(record_path)
            except OSError:
                mtime = 0
            entries.append((mtime, job_id))
        if len(entries) <= constants.KEEP_LAST_N:
            return
        entries.sort()
        excess = len(entries) - constants.KEEP_LAST_N
        for _, job_id in entries[:excess]:
            self._delete_job_locked(job_id)

    def _delete_job_locked(self, job_id):
        """Delete a job dir under its own flock, re-checking terminal state.

        Guards against a race where the job transitioned to non-terminal
        between the prune scan and this call.

        Returns True if the job dir (and its lock file) was fully removed,
        False if any part of the cleanup was skipped — a job dir that can't
        be read/locked/removed is simply left in place, not pruned, and the
        reason is logged at debug level.
        """
        job_dir = self.job_dir(job_id)
        lock_path = self._lock_path(job_id)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                record = self.read(job_id)
            except (OSError, ValueError):
                record = None
            if record is not None and record.get("state") not in TERMINAL_STATES:
                return
            try:
                for root, dirs, files in os.walk(job_dir, topdown=False):
                    for name in files:
                        if os.path.join(root, name) == lock_path:
                            continue
                        os.unlink(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
            except OSError:
                return
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        try:
            os.unlink(lock_path)
        except OSError as exc:
            logging.debug(
                "delegate: prune: could not remove lock file %s for job %s, "
                "leaving job dir in place: %s",
                lock_path,
                job_id,
                exc,
            )
            return False
        try:
            os.rmdir(job_dir)
        except OSError as exc:
            logging.debug(
                "delegate: prune: job dir %s not empty/removable for job %s, "
                "not pruned: %s",
                job_dir,
                job_id,
                exc,
            )
            return False
        return True
