"""Crash recovery and orphan reaping for delegate jobs."""

import json
import time

from . import process
from .jobstore_states import NON_TERMINAL_STATES

_DISPATCH_OWNERSHIP_PHASES = {"spawned", "worker_owned", "backend_started"}


class JobReaperMixin:
    """Recover or terminalize jobs whose worker ownership disappeared."""

    def reap_if_dead(self, job_id):
        """Recover a job whose worker lock disappeared, or fail it closed."""
        record = self.read(job_id)
        if record.get("state") not in NON_TERMINAL_STATES:
            self._reap_cancelled_orphan(job_id, record)
            return record
        if process._worker_alive(self, job_id, record):
            return record
        age = time.time() - record.get("created_at", 0)
        if age < process.WORKER_STARTUP_GRACE_SECONDS:
            return record

        exclusion_result = self._resolve_launch_exclusion(job_id, record)
        if exclusion_result is not None:
            return exclusion_result
        self._reap_backend_orphan(job_id, record)

        restored = self._restore_recoverable_fallback(job_id, record)
        if restored is not None:
            return restored
        if self._has_unproven_dispatch(record):
            return self._mark_dispatch_unknown(
                job_id,
                record,
                "backend dispatch ownership could not be proven",
            )
        return self._mark_failed(job_id)

    def _reap_cancelled_orphan(self, job_id, record):
        if record.get("state") == "cancelled" and process._has_pgid_tracking(
            self, job_id, record
        ):
            process._reap_cancelled_orphan(self, job_id, record)

    def _resolve_launch_exclusion(self, job_id, record):
        launch_exclusion = self._read_launch_exclusion_for_reap(job_id)
        if launch_exclusion is None:
            return None
        dispatch = record.get("dispatch")
        if self._dispatch_matches_exclusion(dispatch, launch_exclusion):
            self.clear_launch_exclusion(job_id, launch_exclusion)
            return None
        return self._mark_dispatch_unknown(
            job_id,
            record,
            "worker launch exclusion remained unresolved",
            launch_exclusion=launch_exclusion,
        )

    def _read_launch_exclusion_for_reap(self, job_id):
        try:
            return self.read_launch_exclusion(job_id)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, json.JSONDecodeError):
            return {"attempt_id": None, "recovery_id": None}

    @staticmethod
    def _dispatch_matches_exclusion(dispatch, launch_exclusion):
        return (
            isinstance(dispatch, dict)
            and dispatch.get("phase") == "spawned"
            and dispatch.get("attempt_id") == launch_exclusion.get("attempt_id")
            and dispatch.get("process_start_identity")
            == launch_exclusion.get("process_start_identity")
        )

    def _reap_backend_orphan(self, job_id, record):
        pgid = record.get("pgid") or process._read_pgid_file(self.job_dir(job_id))
        if pgid and process._backend_alive(self, job_id):
            process._kill_pgid(self, job_id, pgid)

    def _restore_recoverable_fallback(self, job_id, record):
        recovery = record.get("recovery")
        if not isinstance(recovery, dict):
            return None
        try:
            stored_recovery = self.read_recovery(job_id)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        dispatch = record.get("dispatch")
        if not (
            stored_recovery == recovery
            and isinstance(dispatch, dict)
            and dispatch.get("phase") == "spawned"
            and process._spawned_worker_gone(self, job_id, record)
        ):
            return None

        def _restore_pending(current):
            if current.get("state") not in NON_TERMINAL_STATES:
                return None
            current["state"] = "fallback_pending"
            current["fallback_pending"] = True
            current.pop("worker_pid", None)
            current.pop("foreground", None)
            current["pgid"] = None
            return current

        return self.mutate(job_id, _restore_pending)

    @staticmethod
    def _has_unproven_dispatch(record):
        dispatch = record.get("dispatch")
        return isinstance(dispatch, dict) and dispatch.get("phase") in (
            _DISPATCH_OWNERSHIP_PHASES
        )

    def _mark_dispatch_unknown(
        self,
        job_id,
        record,
        reason,
        *,
        launch_exclusion=None,
    ):
        identity = launch_exclusion or record.get("dispatch") or {}
        audit = {
            "attempt_id": identity.get("attempt_id"),
            "recovery_id": identity.get("recovery_id")
            if launch_exclusion is not None
            else (record.get("recovery") or {}).get("recovery_id"),
            "reason": reason,
            "resumable": False,
        }
        self.write_dispatch_unknown_audit(job_id, audit)

        def _dispatch_unknown(current):
            if current.get("state") not in NON_TERMINAL_STATES:
                return None
            current["state"] = "dispatch_unknown"
            current["fallback_pending"] = False
            current["error"] = reason
            current["recovery_audit"] = audit
            return current

        return self.mutate(job_id, _dispatch_unknown)

    def _mark_failed(self, job_id):
        def _mark(current):
            if current.get("state") not in NON_TERMINAL_STATES:
                return None
            current["state"] = "failed"
            current["error"] = "process died without result"
            return current

        return self.mutate(job_id, _mark)
