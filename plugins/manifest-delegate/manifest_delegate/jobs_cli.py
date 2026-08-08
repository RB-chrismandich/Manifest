"""manifest-delegate: jobs_cli."""

import json
import os
import signal
import sys
import time

from . import backend, constants, jobstore, process, task


def cmd_status(args):
    store = jobstore.JobStore()
    if not args.job_id:
        rows = []
        for job_id in store.list_job_ids():
            try:
                rows.append(store.reap_if_dead(job_id))
            except (OSError, ValueError):
                continue
        if args.json:
            print(json.dumps(rows))
        else:
            for rec in rows:
                print(
                    "{}  {}  {}  {}".format(
                        rec["job_id"][:12],
                        rec.get("kind", "task"),
                        rec.get("backend"),
                        rec.get("state"),
                    )
                )
        return 0

    resolved, error = task._resolve_job_id(store, args.job_id)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2

    deadline = (
        time.time() + (args.timeout or backend.DEFAULT_BUDGET_SECONDS)
        if args.wait
        else None
    )
    record = store.reap_if_dead(resolved)
    while args.wait and record.get("state") not in jobstore.TERMINAL_STATES:
        if deadline and time.time() >= deadline:
            break
        time.sleep(0.5)
        record = store.reap_if_dead(resolved)

    if args.json:
        print(json.dumps(record))
    else:
        print("job_id: {}".format(record["job_id"]))
        print("backend: {}".format(record.get("backend")))
        print("state: {}".format(record.get("state")))
    return 0


def cmd_result(args):
    store = jobstore.JobStore()
    if not args.job_id:
        print("delegate: job id or prefix required", file=sys.stderr)
        return 2
    resolved, error = task._resolve_job_id(store, args.job_id)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2

    record = store.reap_if_dead(resolved)
    if record.get("state") not in jobstore.TERMINAL_STATES:
        print(
            f"delegate: still running; delegate.py status {resolved} --wait",
            file=sys.stderr,
        )
        return 1

    job_dir = store.job_dir(resolved)
    output_path = os.path.join(job_dir, "output.txt")
    envelope = record.get("envelope") or {
        "outcome": "failure",
        "error": record.get("error", "no envelope recorded"),
    }
    if args.json:
        payload = dict(envelope)
        payload["raw_output_path"] = output_path
        print(json.dumps(payload))
    else:
        print("outcome: {}".format(envelope.get("outcome")))
        if envelope.get("error"):
            print("error: {}".format(envelope["error"]))
        print(f"raw_output_path: {output_path}")
    return 0


def _terminate_job_processes(store, job_id, record):
    """Kill every process a cancel could leave running for `job_id`, across all
    race windows. Returns True if any live process/group was killed.

    Order: (1) the recorded backend pgid, (2) the worker itself — but ONLY when
    _worker_alive confirms via the lifetime flock that record['worker_pid'] is
    genuinely our worker, never a recycled pid. If the worker is confirmed dead
    the backend it may have forked is handled independently (record/crash-safe
    pgid); if it is mid-fork before locking, the atomic queued->running claim
    still stops the backend, so skipping the signal is safe. Callers then
    transition state and call _reap_raced_pgid for a pgid that may have been
    persisted after this initial read."""
    killed = False
    pgid = record.get("pgid")
    if pgid and process._backend_alive(store, job_id):
        process._kill_pgid(store, job_id, pgid)
        killed = True
    # Never SIGKILL a foreground job's worker_pid: it is the interactive CLI
    # process the user is running. Killing its backend group (above) stops the
    # work; the CLI then observes the terminal state and exits cleanly. Only a
    # background worker (a separate process we spawned) is safe to signal.
    if not record.get("foreground") and process._worker_alive(store, job_id, record):
        try:
            os.kill(record["worker_pid"], signal.SIGKILL)
        except OSError as exc:
            constants.err(
                "job {}: failed to kill worker pid {}: {}".format(
                    job_id, record["worker_pid"], exc
                )
            )
    return killed


# How long to wait for a forked-but-not-yet-published backend pgid to appear
# while backend.lock is still held (the publication race below). Bounded so a
# cancel cannot hang; only paid when a backend provably exists but is mid-launch.
_RACED_PGID_PUBLISH_TIMEOUT_SECONDS = 3.0


def _reap_raced_pgid(store, job_id, before_pgid):
    """After the cancel state transition, kill a backend pgid that appeared in
    the race — from record.json (worker persisted it late) or the crash-safe
    <job_dir>/backend.pgid file (worker died in the Popen->persist window before
    it could persist). Returns True if a live group was killed.

    Publication race (codex round 8): the worker can be SIGKILLed after Popen
    has forked the backend — which inherited backend.lock, held — but BEFORE the
    child wrote its pgid to backend.pgid in preexec. A held backend.lock means a
    backend genuinely EXISTS even though its pgid is not yet published, so a
    single read here would miss it and the caller's _clear_pgid_tracking would
    orphan a write-capable process. Use the lock as the launch handshake: while
    it stays held and no pgid has appeared, wait a bounded time for the child to
    publish, then kill the group."""
    post = store.read(job_id)
    raced = post.get("pgid")
    if raced and raced != before_pgid and process._backend_alive(store, job_id):
        process._kill_pgid(store, job_id, raced)
        return True
    if post.get("pgid"):
        return False
    job_dir = store.job_dir(job_id)
    file_pgid = process._read_pgid_file(job_dir)
    deadline = time.monotonic() + _RACED_PGID_PUBLISH_TIMEOUT_SECONDS
    while (
        not file_pgid
        and process._backend_alive(store, job_id)
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
        file_pgid = process._read_pgid_file(job_dir)
    if file_pgid and process._backend_alive(store, job_id):
        process._kill_pgid(store, job_id, file_pgid)
        return True
    return False


def cmd_cancel(args):
    store = jobstore.JobStore()
    if args.job_id:
        resolved, error = task._resolve_job_id(store, args.job_id)
    else:
        resolved, error = task._resolve_sole_active(store)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2

    record = store.read(resolved)
    if record.get("state") in jobstore.TERMINAL_STATES:
        if args.json:
            print(json.dumps(record))
        else:
            print(f"job_id: {resolved}")
            print("state: {} (already terminal, no-op)".format(record.get("state")))
        return 0

    before_pgid = record.get("pgid")
    was_alive = _terminate_job_processes(store, resolved, record)

    def _mark_cancelled(rec):
        if rec.get("state") in jobstore.TERMINAL_STATES:
            return None
        rec["state"] = "cancelled"
        return rec

    record = store.mutate(resolved, _mark_cancelled)
    if _reap_raced_pgid(store, resolved, before_pgid):
        was_alive = True
    # Every backend for this job is now killed; erase the pgid tracking so no
    # later reap/status re-derives the now-dead pgid and SIGKILLs a recycled one.
    process._clear_pgid_tracking(store, resolved)
    if args.json:
        payload = dict(record)
        payload["was_alive"] = was_alive
        print(json.dumps(payload))
    else:
        print(f"job_id: {resolved}")
        print("state: {}".format(record.get("state")))
        print(f"process_was_alive: {was_alive}")
    return 0
