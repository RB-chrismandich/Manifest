"""manifest-delegate: jobstore."""

import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import time
import uuid

from . import constants, process

# ---------------------------------------------------------------------------
# Job-record store (data-model.md)
# ---------------------------------------------------------------------------

TERMINAL_STATES = {"completed", "failed", "timeout", "cancelled"}
NON_TERMINAL_STATES = {"queued", "running"}


def workspace_slug(cwd=None):
    cwd = cwd or os.getcwd()
    base = os.path.basename(os.path.normpath(cwd)) or "workspace"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower() or "workspace"
    digest = hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


def delegations_root():
    override = os.environ.get(constants.DELEGATIONS_DIR_ENV)
    if override:
        return override
    return os.path.expanduser("~/.claude/.agent_outputs/delegations")


def _mkdir_0700(path):
    os.makedirs(path, exist_ok=True)
    os.chmod(path, stat.S_IRWXU)


def _write_0600(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    finally:
        pass
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _atomic_write_0600(path, content):
    """Write content to path atomically: tmp file (0600) + fsync + os.replace.

    If path already exists and is readable, best-effort back it up to
    ``<path>.bak`` before the replace so a bad write is always recoverable.
    """
    directory = os.path.dirname(path) or "."
    if os.path.isfile(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except OSError as exc:
            # Best-effort backup; never block the write on this, but the
            # operator should still know the .bak safety net didn't land.
            constants.err(f"warning: could not create backup {path}.bak ({exc})")
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError as cleanup_exc:
            constants.err(
                f"warning: could not remove temp file {tmp_path} ({cleanup_exc})"
            )
        raise


class JobStore:
    """Per-job record directories with CAS-locked record.json mutation."""

    def __init__(self, cwd=None, root=None):
        self.workspace_dir = os.path.join(
            root or delegations_root(), workspace_slug(cwd)
        )
        _mkdir_0700(self.workspace_dir)

    def job_dir(self, job_id):
        return os.path.join(self.workspace_dir, job_id)

    def create(self, backend_id, extra=None):
        job_id = uuid.uuid4().hex
        job_dir = self.job_dir(job_id)
        _mkdir_0700(job_dir)
        record = {
            "job_id": job_id,
            "backend": backend_id,
            "state": "queued",
            "pgid": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        if extra:
            record.update(extra)
        _write_0600(os.path.join(job_dir, "record.json"), json.dumps(record, indent=2))
        _write_0600(os.path.join(job_dir, "output.txt"), "")
        _write_0600(os.path.join(job_dir, "job.log"), "")
        self._prune()
        return record

    def _lock_path(self, job_id):
        return os.path.join(self.job_dir(job_id), ".lock")

    def read(self, job_id):
        record_path = os.path.join(self.job_dir(job_id), "record.json")
        with open(record_path, encoding="utf-8") as fh:
            return json.load(fh)

    def mutate(self, job_id, mutator):
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
            fd, tmp_path = tempfile.mkstemp(
                dir=job_dir, prefix=".record.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(updated, indent=2))
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
                os.rename(tmp_path, record_path)
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

    def _pgid_alive(self, pgid):
        if not pgid:
            return False
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError as exc:
            return exc.errno != errno.ESRCH

    def reap_if_dead(self, job_id):
        """If the recorded worker/pgid is dead and the job is non-terminal,
        kill any surviving backend pgid and mark the job failed."""
        record = self.read(job_id)
        if record.get("state") not in NON_TERMINAL_STATES:
            # Terminal already, but a cancel that raced a backend fork can leave
            # the detached process group alive after the record was frozen. Reap
            # that orphan ONCE, then clear the pgid and the crash-safe file so no
            # later pass re-probes: a recycled pgid must never be re-killed.
            if record.get("state") == "cancelled" and process._has_pgid_tracking(
                self, job_id, record
            ):
                process._reap_cancelled_orphan(self, job_id, record)
            return record
        # Liveness via the worker's lifetime flock, not os.kill(worker_pid, 0):
        # a recycled pid would answer the signal-0 probe and falsely read alive.
        if process._worker_alive(self, job_id, record):
            return record

        # Startup grace: between job creation and the worker acquiring its
        # lifetime lock, the worker is not yet confirmable-alive but the job is
        # NOT dead — it is still starting. Reaping here would fail a live job
        # (observable when parallel sessions share a workspace). Give the worker
        # WORKER_STARTUP_GRACE_SECONDS to publish its lock before we treat a
        # missing worker as death.
        age = time.time() - record.get("created_at", 0)
        if age < process.WORKER_STARTUP_GRACE_SECONDS:
            return record

        pgid = record.get("pgid") or process._read_pgid_file(self.job_dir(job_id))
        if pgid and process._backend_alive(self, job_id):
            process._kill_pgid(self, job_id, pgid)

        def _mark_failed(rec):
            if rec.get("state") not in NON_TERMINAL_STATES:
                return None
            rec["state"] = "failed"
            rec["error"] = "process died without result"
            return rec

        return self.mutate(job_id, _mark_failed)

    def list_job_ids(self):
        if not os.path.isdir(self.workspace_dir):
            return []
        return [
            name
            for name in os.listdir(self.workspace_dir)
            if os.path.isdir(os.path.join(self.workspace_dir, name))
        ]

    def _prune(self):
        """Delete oldest terminal jobs beyond KEEP_LAST_N.

        Non-terminal (queued/running) jobs are never prune candidates and
        never count toward the KEEP_LAST_N cap, regardless of age.
        """
        job_ids = self.list_job_ids()
        entries = []
        for job_id in job_ids:
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
