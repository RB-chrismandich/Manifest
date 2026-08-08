"""manifest-delegate: worker."""

import os
import subprocess
import sys

from . import backend, constants, envelope, jobstore, process, registry


def _run_backend_and_finish(store, job_id, entry, record, prompt_bytes):
    job_dir = store.job_dir(job_id)
    mapping = {"output_file": os.path.join(job_dir, "output.txt")}
    resume_from = record.get("resume_from_session_ref")
    if resume_from and entry.get("resume"):
        argv = backend.build_resume_argv(
            entry, resume_from, record.get("write", False), record.get("model"), mapping
        )
    else:
        argv = backend.build_invoke_argv(
            entry, record.get("write", False), record.get("model"), mapping
        )
    budget = record.get("budget_seconds", backend.DEFAULT_BUDGET_SECONDS)

    returncode, raw_output, pgid, timed_out, session_ref = process._spawn_backend(
        entry,
        argv,
        prompt_bytes,
        job_dir,
        budget,
        on_pgid=process._make_pgid_persister(store, job_id),
    )
    jobstore._write_0600(os.path.join(job_dir, "output.txt"), raw_output)
    # Not `envelope = ...`: that would shadow the `envelope` module for the rest
    # of this function.
    result_envelope = envelope.normalize_envelope(
        raw_output, entry["id"], record.get("model")
    )
    if session_ref is None and entry.get("resume"):
        constants.err(
            "backend {!r} produced no capturable session id this run "
            "(session_id_capture found nothing); a follow-up will start fresh".format(
                entry["id"]
            )
        )
    if timed_out:
        final_state = "timeout"
    elif returncode == 0 and result_envelope.get("outcome") != "failure":
        final_state = "completed"
    else:
        final_state = "failed"

    def _finish(rec):
        if rec.get("state") in jobstore.TERMINAL_STATES:
            return None
        rec["state"] = final_state
        rec["envelope"] = result_envelope
        rec["pgid"] = pgid
        rec["returncode"] = returncode
        if session_ref:
            rec["session_ref"] = session_ref
        return rec

    return store.mutate(job_id, _finish)


def _spawn_worker(store, job_id):
    proc = subprocess.Popen(
        [
            sys.executable,
            constants.ENTRY_SCRIPT,
            "_worker",
            job_id,
            store.workspace_dir,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    store.mutate(job_id, lambda rec: dict(rec, worker_pid=proc.pid))


def _run_backend_foreground(store, job_id, entry, record, prompt_bytes):
    """Run a backend synchronously in THIS (CLI) process, taking the same
    ownership a background worker does: record this pid as the worker and hold
    the lifetime lock. Without this a long-running foreground delegation has no
    worker pid or lock, so after WORKER_STARTUP_GRACE_SECONDS a concurrent
    status/SessionEnd reap from another session sharing the workspace would see
    it as dead and kill its backend (codex round-3 finding). The lock is held
    for the CLI process lifetime and released on exit, after which a genuinely
    crashed foreground job becomes reapable again."""
    # `foreground=True` marks worker_pid as THIS interactive CLI process, so
    # cancel/terminate kills only the backend group and never SIGKILLs the CLI
    # the user is running (a background worker_pid, by contrast, is killable).
    owned = store.mutate(
        job_id, lambda rec: dict(rec, worker_pid=os.getpid(), foreground=True)
    )
    process._acquire_worker_lifetime_lock(store.job_dir(job_id))
    return _run_backend_and_finish(store, job_id, entry, owned, prompt_bytes)


def cmd_worker(job_id, workspace_dir):
    store = jobstore.JobStore.__new__(jobstore.JobStore)
    store.workspace_dir = workspace_dir
    try:
        record = store.read(job_id)
    except (OSError, ValueError):
        return 1
    backends = registry.load_registry_or_exit(backend._registry_path_override())
    entry = registry.resolve_backend(backends, record["backend"])
    if entry is None:
        store.mutate(
            job_id,
            lambda rec: dict(
                rec, state="failed", error="backend no longer in registry"
            ),
        )
        return 1
    job_dir = store.job_dir(job_id)
    # Hold the lifetime lock before the claim so any cancel/reap that observes
    # this worker's pid can verify it is really us (not a recycled pid).
    process._acquire_worker_lifetime_lock(job_dir)
    with open(os.path.join(job_dir, "prompt.txt"), encoding="utf-8") as fh:
        prompt_bytes = fh.read().encode("utf-8")
    claimed = store.mutate(
        job_id,
        lambda rec: (
            dict(rec, state="running")
            if rec.get("state") not in jobstore.TERMINAL_STATES
            else None
        ),
    )
    if claimed.get("state") != "running":
        # Claim lost the race (job already cancelled/terminal): do not start
        # the backend.
        return 1
    _run_backend_and_finish(store, job_id, entry, claimed, prompt_bytes)
    return 0
