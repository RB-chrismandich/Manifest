"""Worker ownership, launch, and foreground/background entry points."""

import os
import subprocess
import tempfile
import time
import uuid

from . import backend, constants, jobstore, process, registry
from .worker_backend import (
    _allowlisted_task_failure as _allowlisted_task_failure,
)
from .worker_backend import (
    _build_backend_invocation as _build_backend_invocation,
)
from .worker_backend import (
    _confirm_fallback as _confirm_fallback,
)
from .worker_backend import (
    _run_backend_and_finish as _run_backend_and_finish,
)


class DispatchUnknownPersistenceError(RuntimeError):
    """An unproven launch could not be durably marked non-resumable."""


def _restore_fallback_pending(
    store, job_id, recovery, failure_summary, *, attempts=None
):
    """Restore task-free recovery after a claimed continuation cannot spawn."""
    if not isinstance(recovery, dict):
        return store.read(job_id)
    current = store.read(job_id)
    if (
        current.get("state") == "dispatch_unknown"
        or store.has_dispatch_unknown_audit(job_id)
        or store.has_launch_exclusion(job_id)
        or current.get("recovery") != recovery
    ):
        return current
    dispatch = current.get("dispatch")
    if isinstance(dispatch, dict) and dispatch.get("phase") in {
        "worker_owned",
        "backend_started",
        "terminal",
        "dispatch_unknown",
    }:
        return current
    store.write_recovery(job_id, recovery)

    def _restore(record):
        if record.get("state") in jobstore.TERMINAL_STATES:
            return None
        record["state"] = "fallback_pending"
        record["fallback_pending"] = True
        record["recovery"] = recovery
        record["failure_summary"] = failure_summary or {}
        if attempts is not None:
            record["model_attempts"] = attempts
        for key in (
            "worker_pid",
            "worker_pgid",
            "worker_start_identity",
            "foreground",
            "dispatch",
        ):
            record.pop(key, None)
        return record

    return store.mutate(job_id, _restore, expected_version=current["version"])


def _commit_continuation_claim(store, job_id):
    current = store.read(job_id)
    recovery = current.get("recovery")
    failure_summary = current.get("failure_summary")
    if not isinstance(recovery, dict):
        return current, None, None

    def _commit(record):
        record["fallback_pending"] = False
        return record

    claimed = store.mutate(job_id, _commit, expected_version=current["version"])
    return claimed, recovery, failure_summary


def _read_spawn_prompt(store, job_id, prompt_bytes):
    if prompt_bytes is not None:
        return prompt_bytes
    with open(os.path.join(store.job_dir(job_id), "prompt.txt"), "rb") as stream:
        stored = stream.read(backend.TASK_LIMIT + 1)
    if len(stored) > backend.TASK_LIMIT:
        raise ValueError("stored review prompt exceeds the 1 MiB task limit")
    return stored


def _launch_exclusion(current, attempt_id, start_identity):
    return {
        "attempt_id": attempt_id,
        "recovery_id": (current.get("recovery") or {}).get("recovery_id"),
        "process_start_identity": start_identity,
        "resumable": False,
    }


def _popen_worker(store, job_id, prompt, attempt_id, start_identity):
    return subprocess.Popen(
        constants.worker_argv(
            job_id,
            store.workspace_dir,
            str(prompt.fileno()),
            attempt_id,
            start_identity,
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        pass_fds=(prompt.fileno(),),
    )


def _record_spawned_worker(store, job_id, current, proc, attempt_id, start_identity):
    worker_pgid = os.getpgid(proc.pid)

    def _spawned(record):
        if record.get("state") in jobstore.TERMINAL_STATES:
            return None
        record["attempt_id"] = attempt_id
        record["worker_pid"] = proc.pid
        record["worker_pgid"] = worker_pgid
        record["worker_start_identity"] = start_identity
        record["dispatch"] = {
            "phase": "spawned",
            "attempt_id": attempt_id,
            "job_version": record.get("version", 1) + 1,
            "pid": proc.pid,
            "pgid": worker_pgid,
            "process_start_identity": start_identity,
        }
        return record

    return store.mutate(job_id, _spawned, expected_version=current.get("version"))


def _persist_unknown_launch(store, job_id, current, proc, attempt_id, start_identity):
    audit = {
        "attempt_id": attempt_id,
        "recovery_id": (current.get("recovery") or {}).get("recovery_id"),
        "reason": "worker launch outcome is unknown",
        "resumable": False,
    }
    try:
        store.write_dispatch_unknown_audit(job_id, audit)
    except Exception as error:
        raise DispatchUnknownPersistenceError(
            "dispatch_unknown audit persistence failed closed"
        ) from error

    def _unknown(record):
        record["state"] = "dispatch_unknown"
        record["fallback_pending"] = False
        record["error"] = "worker launch outcome is unknown"
        record["recovery_audit"] = audit
        record["dispatch"] = {
            "phase": "dispatch_unknown",
            "attempt_id": attempt_id,
            "pid": proc.pid,
            "pgid": getattr(proc, "pid", None),
            "process_start_identity": start_identity,
        }
        return record

    try:
        store.mutate(job_id, _unknown)
    except Exception as error:
        raise DispatchUnknownPersistenceError(
            "dispatch_unknown persistence failed closed"
        ) from error


def _handle_spawn_checkpoint_failure(
    store, job_id, current, proc, attempt_id, start_identity, exclusion
):
    if process._terminate_and_reap_worker(proc):
        store.clear_launch_exclusion(job_id, exclusion)
        return
    _persist_unknown_launch(store, job_id, current, proc, attempt_id, start_identity)


def _spawn_worker(store, job_id, prompt_bytes=None):
    """Launch one detached worker behind a durable exclusion boundary."""
    prompt_bytes = _read_spawn_prompt(store, job_id, prompt_bytes)
    current = store.read(job_id)
    attempt_id = current.get("attempt_id") or uuid.uuid4().hex
    start_identity = uuid.uuid4().hex
    exclusion = _launch_exclusion(current, attempt_id, start_identity)
    store.write_launch_exclusion(job_id, exclusion)
    with tempfile.TemporaryFile() as prompt:
        prompt.write(prompt_bytes)
        prompt.seek(0)
        try:
            proc = _popen_worker(store, job_id, prompt, attempt_id, start_identity)
        except Exception:
            store.clear_launch_exclusion(job_id, exclusion)
            raise
        try:
            spawned = _record_spawned_worker(
                store, job_id, current, proc, attempt_id, start_identity
            )
            store.clear_launch_exclusion(job_id, exclusion)
            return spawned
        except Exception:
            _handle_spawn_checkpoint_failure(
                store,
                job_id,
                current,
                proc,
                attempt_id,
                start_identity,
                exclusion,
            )
            raise


def _run_backend_foreground(store, job_id, entry, record, prompt_bytes):
    """Run synchronously while publishing verifiable worker ownership."""
    attempt_id = record.get("attempt_id") or uuid.uuid4().hex
    start_identity = uuid.uuid4().hex
    pgid = os.getpgid(0)

    def _claim(current):
        current["attempt_id"] = attempt_id
        current["worker_pid"] = os.getpid()
        current["worker_pgid"] = pgid
        current["worker_start_identity"] = start_identity
        current["foreground"] = True
        current["dispatch"] = {
            "phase": "worker_owned",
            "attempt_id": attempt_id,
            "job_version": current.get("version", 1) + 1,
            "pid": os.getpid(),
            "pgid": pgid,
            "process_start_identity": start_identity,
        }
        return current

    store.mutate(job_id, _claim)
    process._acquire_worker_lifetime_lock(store.job_dir(job_id))
    process._publish_worker_identity(store.job_dir(job_id), start_identity)
    claimed, recovery, failure_summary = _commit_continuation_claim(store, job_id)
    try:
        return _run_backend_and_finish(store, job_id, entry, claimed, prompt_bytes)
    except Exception:
        if recovery is not None:
            _restore_fallback_pending(store, job_id, recovery, failure_summary)
        raise


def _wait_for_spawned_record(store, job_id, attempt_id, start_identity):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        candidate = store.read(job_id)
        dispatch = candidate.get("dispatch")
        if (
            isinstance(dispatch, dict)
            and dispatch.get("phase") == "spawned"
            and dispatch.get("attempt_id") == attempt_id
            and dispatch.get("process_start_identity") == start_identity
            and dispatch.get("pid") == os.getpid()
        ):
            return candidate
        if candidate.get("state") in jobstore.TERMINAL_STATES:
            return None
        time.sleep(0.01)
    return None


def _claim_spawned_record(store, job_id, spawned, attempt_id, start_identity):
    def _own(record):
        dispatch = record.get("dispatch")
        if (
            not isinstance(dispatch, dict)
            or dispatch.get("phase") != "spawned"
            or dispatch.get("attempt_id") != attempt_id
            or dispatch.get("process_start_identity") != start_identity
        ):
            return None
        dispatch = dict(dispatch)
        dispatch["phase"] = "worker_owned"
        dispatch["job_version"] = record.get("version", 1) + 1
        record["dispatch"] = dispatch
        record["worker_pid"] = os.getpid()
        record["worker_pgid"] = os.getpgid(0)
        record["worker_start_identity"] = start_identity
        record["attempt_id"] = attempt_id
        return record

    return store.mutate(job_id, _own, expected_version=spawned.get("version"))


def _claim_running(store, job_id):
    return store.mutate(
        job_id,
        lambda record: (
            dict(record, state="running")
            if record.get("state") not in jobstore.TERMINAL_STATES
            else None
        ),
    )


def _run_claimed_worker(store, job_id, entry, prompt_bytes):
    claimed = _claim_running(store, job_id)
    if claimed.get("state") != "running":
        return 1
    claimed, recovery, failure_summary = _commit_continuation_claim(store, job_id)
    try:
        _run_backend_and_finish(store, job_id, entry, claimed, prompt_bytes)
    except Exception:
        if recovery is not None:
            _restore_fallback_pending(store, job_id, recovery, failure_summary)
        return 1
    return 0


def _resolve_worker_entry(store, job_id, record):
    backends = registry.load_registry_or_exit(backend._registry_path_override())
    entry = registry.resolve_backend(backends, record["backend"])
    if entry is not None:
        return entry
    store.mutate(
        job_id,
        lambda current: dict(
            current, state="failed", error="backend no longer in registry"
        ),
    )
    return None


def cmd_worker(
    job_id, workspace_dir, prompt_fd=None, attempt_id=None, start_identity=None
):
    """Claim a spawned worker record and execute its resubmitted task."""
    store = jobstore.JobStore.__new__(jobstore.JobStore)
    store.workspace_dir = workspace_dir
    try:
        record = store.read(job_id)
    except (OSError, ValueError):
        return 1
    entry = _resolve_worker_entry(store, job_id, record)
    if entry is None or not attempt_id or not start_identity:
        return 1
    job_dir = store.job_dir(job_id)
    process._acquire_worker_lifetime_lock(job_dir)
    process._publish_worker_identity(job_dir, start_identity)
    spawned = _wait_for_spawned_record(store, job_id, attempt_id, start_identity)
    if spawned is None:
        return 1
    owned = _claim_spawned_record(store, job_id, spawned, attempt_id, start_identity)
    if (owned.get("dispatch") or {}).get("phase") != "worker_owned":
        return 1
    if prompt_fd is None:
        store.mutate(
            job_id,
            lambda current: dict(
                current, state="failed", error="task resubmission required"
            ),
        )
        return 1
    with os.fdopen(int(prompt_fd), "rb") as stream:
        prompt_bytes = stream.read()
    return _run_claimed_worker(store, job_id, entry, prompt_bytes)
