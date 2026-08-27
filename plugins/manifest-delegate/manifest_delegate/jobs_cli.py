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
    while args.wait and record.get("state") not in jobstore.SETTLED_STATES:
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
        if record.get("state") == "fallback_pending":
            recovery = record.get("recovery") or {}
            print("version: {}".format(record.get("version")))
            print("recovery_id: {}".format(recovery.get("recovery_id")))
            print("next_tier: {}".format(recovery.get("next_tier")))
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
    if record.get("state") not in jobstore.SETTLED_STATES:
        print(
            f"delegate: still running; delegate.py status {resolved} --wait",
            file=sys.stderr,
        )
        return 1

    job_dir = store.job_dir(resolved)
    output_path = os.path.join(job_dir, "output.txt")
    envelope = record.get("envelope") or {
        "outcome": (
            "fallback_pending"
            if record.get("state") == "fallback_pending"
            else "failure"
        ),
        "error": record.get("error", "no envelope recorded"),
    }
    if record.get("state") == "fallback_pending":
        envelope = {
            **envelope,
            "job_id": record["job_id"],
            "version": record.get("version"),
            "model_attempts": record.get("model_attempts", []),
            "failure_summary": record.get("failure_summary", {}),
            "recovery": record.get("recovery", {}),
        }
    if args.json:
        payload = dict(envelope)
        payload["raw_output_path"] = output_path
        print(json.dumps(payload))
    else:
        print("outcome: {}".format(envelope.get("outcome")))
        if envelope.get("error"):
            print("error: {}".format(envelope["error"]))
        if record.get("state") == "fallback_pending":
            recovery = record.get("recovery") or {}
            print("recovery_id: {}".format(recovery.get("recovery_id")))
            print("next_tier: {}".format(recovery.get("next_tier")))
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


def _resolve_cancel_target(store, args):
    if args.job_id:
        resolved, error = task._resolve_job_id(store, args.job_id)
    else:
        resolved, error = task._resolve_sole_active(store)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return None, 2
    return resolved, None


def _validate_cancel_version(record, expected):
    if expected is None or record.get("version") == expected:
        return None
    print(
        "delegate: stale job version: expected {}, found {}".format(
            expected, record.get("version")
        ),
        file=sys.stderr,
    )
    return 2


def _cancel_fallback(store, resolved, record, args, expected):
    if record.get("state") not in {"fallback_pending", "fallback_rejected"}:
        return None
    recovery_id = getattr(args, "recovery_id", None)
    if expected is None or not recovery_id:
        print(
            "delegate: cancelling fallback_pending requires "
            "--expected-version and --recovery-id",
            file=sys.stderr,
        )
        return 2
    try:
        record = store.reject_fallback(
            resolved,
            expected_version=expected,
            recovery_id=recovery_id,
            action="cancel",
        )
    except (OSError, ValueError) as error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(record))
    else:
        print(f"job_id: {resolved}")
        print("state: fallback_rejected")
    return 0


def _render_cancelled(args, resolved, record, was_alive):
    if args.json:
        payload = dict(record)
        payload["was_alive"] = was_alive
        print(json.dumps(payload))
        return
    print(f"job_id: {resolved}")
    print("state: {}".format(record.get("state")))
    print(f"process_was_alive: {was_alive}")


def _cancel_active(store, resolved, record, args, expected):
    before_pgid = record.get("pgid")

    def _mark_cancelled(rec):
        if rec.get("state") in jobstore.TERMINAL_STATES:
            return None
        rec["state"] = "cancelled"
        return rec

    # Mark terminal BEFORE killing. _claim_running refuses a record already in
    # a TERMINAL state, so a worker that has not yet claimed can no longer
    # spawn a backend once this CAS lands -- which is the barrier
    # _terminate_job_processes' docstring already relies on ("if it is mid-fork
    # before locking, the atomic queued->running claim still stops the
    # backend"). Killing first left a window between the kill (which finds
    # nothing, because nothing has spawned yet) and this CAS, in which the
    # worker could claim queued->running and fork a backend that no guard then
    # reliably reaped: _reap_raced_pgid can miss a backend forked but not yet
    # published while backend.lock is not yet held, so its bounded wait exits
    # immediately and _clear_pgid_tracking orphans it.
    #
    # Reproduced at ~1 in 24 runs under parallel load (#846) as a job that
    # reached state "cancelled" with was_alive False -- cancel found nothing to
    # kill -- while the stub backend's start sentinel existed, proving the
    # executable ran anyway.
    #
    # A stale-version CAS failure now returns before any kill, which is also
    # the safer order: this process has not cancelled the job, so it has no
    # business killing its processes.
    try:
        record = store.mutate(resolved, _mark_cancelled, expected_version=expected)
    except (OSError, ValueError) as error:
        # The worker can finalize the job between the pre-check read and this
        # CAS, bumping the version. Report it like every other stale-version
        # path instead of surfacing a traceback.
        print(f"delegate: {error}", file=sys.stderr)
        return 2
    was_alive = _terminate_job_processes(store, resolved, record)
    if _reap_raced_pgid(store, resolved, before_pgid):
        was_alive = True
    process._clear_pgid_tracking(store, resolved)
    _render_cancelled(args, resolved, record, was_alive)
    return 0


def cmd_cancel(args):
    store = jobstore.JobStore()
    resolved, failure = _resolve_cancel_target(store, args)
    if failure is not None:
        return failure

    record = store.read(resolved)
    expected = getattr(args, "expected_version", None)
    version_failure = _validate_cancel_version(record, expected)
    if version_failure is not None:
        return version_failure
    fallback_result = _cancel_fallback(store, resolved, record, args, expected)
    if fallback_result is not None:
        return fallback_result
    if record.get("state") in jobstore.TERMINAL_STATES:
        if args.json:
            print(json.dumps(record))
        else:
            print(f"job_id: {resolved}")
            print("state: {} (already terminal, no-op)".format(record.get("state")))
        return 0
    return _cancel_active(store, resolved, record, args, expected)
