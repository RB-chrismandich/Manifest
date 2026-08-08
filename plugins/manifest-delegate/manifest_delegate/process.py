"""manifest-delegate: process."""

import contextlib
import fcntl
import os
import signal
import subprocess
import threading

from . import backend, constants

BACKEND_PGID_FILENAME = "backend.pgid"
BACKEND_LOCK_FILENAME = "backend.lock"
WORKER_LOCK_FILENAME = "worker.lock"

# Worker-held lock fds, kept open for the worker process's lifetime so the
# kernel releases them only on exit. Never closed explicitly.
_WORKER_LOCK_FDS = []


def _acquire_worker_lifetime_lock(job_dir):
    """Called once at worker startup: hold an exclusive flock on worker.lock for
    the whole process lifetime. Because the kernel releases an flock only when
    the holding process exits, the lock's held-ness is a pid-reuse-proof liveness
    signal — unlike os.kill(pid, 0), which a recycled pid would answer for."""
    fd = os.open(
        os.path.join(job_dir, WORKER_LOCK_FILENAME), os.O_CREAT | os.O_RDWR, 0o600
    )
    fcntl.flock(fd, fcntl.LOCK_EX)
    _WORKER_LOCK_FDS.append(fd)


def _worker_alive(store, job_id, record):
    """True iff THIS job's worker process is still running, proven by the
    worker.lock flock rather than os.kill(worker_pid, 0) — so a recycled pid can
    never be mistaken for a live worker. A missing lock file means the worker was
    recorded but has not yet acquired its lock (a sub-millisecond startup window);
    treated as not-confirmably-alive, which is safe because the atomic
    queued->running claim independently stops a cancelled job's backend."""
    if not record.get("worker_pid"):
        return False
    lock_path = os.path.join(store.job_dir(job_id), WORKER_LOCK_FILENAME)
    if not os.path.exists(lock_path):
        return False
    fd = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)  # acquired ⇒ no live worker holds it ⇒ dead
        return False
    except OSError:
        return True  # EWOULDBLOCK/EAGAIN ⇒ our worker still holds it
    finally:
        os.close(fd)


def _backend_preexec(job_dir):
    """Return a child preexec_fn that starts a new session (so the backend gets
    its own process group for clean timeout kills) AND writes that group id to
    <job_dir>/backend.pgid before exec. The write happens in the forked child,
    so the pgid is recoverable even if the parent worker is SIGKILLed in the
    window between Popen() returning and the parent's on_pgid persist — closing
    the pre-persist orphan race. Runs post-fork/pre-exec: uses only raw syscalls
    (async-signal-safe-ish), reports nothing (no stdio) and never raises out."""
    pgid_path = os.path.join(job_dir, BACKEND_PGID_FILENAME)

    def _preexec():
        os.setsid()
        fd = os.open(pgid_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.write(fd, str(os.getpgid(0)).encode("ascii"))
        os.close(fd)

    return _preexec


def _backend_alive(store, job_id):
    """True iff this job's backend process group is still running, proven by the
    backend.lock flock (held for the backend's lifetime) rather than
    os.killpg(pgid, 0) — so a recycled pgid is never mistaken for a live backend.
    A missing lock file means no backend is currently holding it (never started,
    or already exited): not confirmably alive."""
    lock_path = os.path.join(store.job_dir(job_id), BACKEND_LOCK_FILENAME)
    if not os.path.exists(lock_path):
        return False
    fd = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)  # acquired ⇒ no live backend holds it ⇒ dead
        return False
    except OSError:
        return True  # EWOULDBLOCK/EAGAIN ⇒ the backend still holds it
    finally:
        os.close(fd)


def _read_pgid_file(job_dir):
    """Crash-safe fallback: the backend pgid the child wrote in preexec, or None.
    Used by cancel/reap when the worker died before persisting pgid to the record."""
    try:
        with open(os.path.join(job_dir, BACKEND_PGID_FILENAME), encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


MAX_CAPTURED_OUTPUT_BYTES = 1_048_576  # 1 MiB retained tail of backend output
DRAIN_GRACE_SECONDS = 5  # bound on waiting for the stdout drain after process exit
WORKER_STARTUP_GRACE_SECONDS = 15  # a job younger than this is "starting", not dead


class _BoundedTail:
    """A thread-safe, size-capped byte tail. The reader thread feeds it
    incrementally so that even if the drain thread is later abandoned (a
    detached descendant holding the pipe open would otherwise block it forever),
    the bytes read so far — including the final fenced envelope emitted before
    the block — are already available to the main thread. Memory is bounded to
    `cap` regardless of total output volume."""

    def __init__(self, cap):
        self._cap = cap
        self._buf = bytearray()
        self._lock = threading.Lock()

    def feed(self, chunk):
        with self._lock:
            self._buf += chunk
            if len(self._buf) > self._cap:
                del self._buf[: len(self._buf) - self._cap]

    def value(self):
        with self._lock:
            return bytes(self._buf)


SESSION_CAPTURE_HEAD_BYTES = (
    262_144  # 256 KiB head retained for early session-id events
)


class _BoundedHead:
    """Thread-safe buffer that keeps only the FIRST `cap` bytes of a stream and
    then stops growing. Session-identification events (e.g. codex's
    `thread.started`) are emitted near the START of the JSONL stream, so the head
    preserves the session ref even when the run emits far more than the tail cap."""

    def __init__(self, cap):
        self._cap = cap
        self._buf = bytearray()
        self._lock = threading.Lock()

    def feed(self, chunk):
        with self._lock:
            room = self._cap - len(self._buf)
            if room > 0:
                self._buf += chunk[:room]

    def value(self):
        with self._lock:
            return bytes(self._buf)


def _drain_into(stream, sinks):
    """Read `stream` to EOF, feeding every sink in `sinks` (each has .feed(bytes)).
    Runs in a daemon thread; if the main thread abandons it (grace exceeded), the
    process exit reaps it."""
    while True:
        try:
            chunk = stream.read(65536)
        except (ValueError, OSError):
            break
        if not chunk:
            break
        for sink in sinks:
            sink.feed(chunk)


def _feed_stdin(stdin, payload):
    """Write `payload` to a subprocess stdin and close it, tolerating a backend
    that closed its end early. Runs in its own thread so a non-draining backend
    cannot deadlock the caller on a full pipe."""
    # A backend that closed its end early is normal, not a fault: whatever it
    # already read is what it acted on, and its captured output is the
    # authoritative record of that. Nothing here is recoverable or worth
    # reporting, so the write is suppressed rather than propagated.
    with contextlib.suppress(BrokenPipeError, OSError):
        stdin.write(payload)
        stdin.close()


def _read_file_tail(path, cap):
    """Return the last `cap` bytes of `path` decoded as text, or '' on error."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > cap:
                fh.seek(size - cap)
            return fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        constants.err(f"job dir: failed to read output tail {path}: {exc}")
        return ""


def _launch_backend(argv, transport, job_dir):
    """Popen the backend with its own session (setsid) holding a lifetime flock.
    The lock fd is opened in the parent and passed via pass_fds (so close_fds
    does not close it); preexec flocks it in the child. Returns (proc, pgid)."""
    stdin_arg = subprocess.PIPE if transport == "stdin" else subprocess.DEVNULL
    # Flock in the PARENT before Popen so there is NO fork->flock window: the
    # child inherits the already-locked open-file description via pass_fds (an
    # flock lives on the description, shared across fork), so backend.lock is held
    # continuously from the instant Popen returns until the backend exits. The
    # parent then closes its copy; the child keeps the description (and the lock).
    lock_fd = os.open(
        os.path.join(job_dir, BACKEND_LOCK_FILENAME), os.O_CREAT | os.O_RDWR, 0o600
    )
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=stdin_arg,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=_backend_preexec(job_dir),
            pass_fds=(lock_fd,),
        )
    finally:
        os.close(lock_fd)  # child holds the locked description; parent's copy is done
    try:
        return proc, os.getpgid(proc.pid)
    except OSError:
        return proc, proc.pid


def _kill_stdout_holder(pgid, proc, job_dir):
    """SIGKILL the descendant still holding stdout after the drain grace.

    Without this, a write-capable orphan outlives its job with NO cancellation
    path — the job becomes terminal `timeout`, which cancel/reap treat as a
    no-op. This is the one place that can still reach it.

    LIMITATION: reaches only descendants that stayed in the backend's process
    group (the realistic runaway child). One that setsid()s into its own group
    escapes killpg, like any daemon a subprocess can spawn; fully containing it
    needs an OS-level lifetime boundary (Linux cgroup / PID namespace) — a
    cross-platform design decision tracked separately, not expressible here.
    """
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError as exc:
        constants.err(
            f"job dir {job_dir}: failed to kill stdout-holding descendant "
            f"pgid {pgid}: {exc}"
        )
    else:
        proc.wait()


def _spawn_backend(entry, argv, prompt_bytes, job_dir, budget, on_pgid=None):
    stdout_path = os.path.join(job_dir, "output.txt")
    with open(os.path.join(job_dir, "job.log"), "a", encoding="utf-8") as log_fh:
        log_fh.write("invoke: {}\n".format(" ".join(argv)))
    transport = (entry.get("input") or {}).get("transport", "stdin")
    proc, pgid = _launch_backend(argv, transport, job_dir)
    if on_pgid:
        on_pgid(pgid)

    # Drain stdout in a thread that keeps only a bounded tail, so peak memory is
    # capped regardless of how much the backend emits. proc.wait enforces the
    # budget independently of output volume.
    tail = _BoundedTail(MAX_CAPTURED_OUTPUT_BYTES)
    head = _BoundedHead(SESSION_CAPTURE_HEAD_BYTES)
    reader = threading.Thread(
        target=_drain_into, args=(proc.stdout, (head, tail)), daemon=True
    )
    reader.start()
    if transport == "stdin":
        # Feed stdin from its own thread: a backend that never drains stdin must
        # not deadlock our write on a full pipe (the reader is draining stdout
        # concurrently, and the timeout below still bounds the whole run).
        writer = threading.Thread(
            target=_feed_stdin, args=(proc.stdin, prompt_bytes), daemon=True
        )
        writer.start()
    timed_out = False
    try:
        proc.wait(timeout=budget)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError as exc:
            constants.err(
                f"job dir {job_dir}: failed to kill timed-out pgid {pgid}: {exc}"
            )
        proc.wait()
    reader.join(DRAIN_GRACE_SECONDS)
    if reader.is_alive():
        # Backend exited but a detached descendant still holds stdout open, so
        # read() stays blocked (closing the fd does NOT reliably interrupt it).
        # Abandon the daemon reader rather than hang past budget (a DoS vector);
        # the envelope emitted before the block is already in the tail. Kill the
        # holder's group and mark the run incomplete.
        _kill_stdout_holder(pgid, proc, job_dir)
        timed_out = True
    raw = tail.value().decode("utf-8", errors="replace")
    output_file_content = (
        _read_file_tail(stdout_path, MAX_CAPTURED_OUTPUT_BYTES)
        if os.path.isfile(stdout_path)
        else ""
    )
    combined = (output_file_content + "\n" + raw) if output_file_content else raw
    # Session ref may scroll out of the 1 MiB tail on large runs, so prefer the
    # retained head (early events) and fall back to the tail.
    session_ref = backend.extract_session_ref(
        entry, head.value().decode("utf-8", errors="replace")
    ) or backend.extract_session_ref(entry, combined)
    return proc.returncode, combined, pgid, timed_out, session_ref


def _kill_pgid(store, job_id, pgid):
    """Best-effort SIGKILL of a backend process group. Shared by the cancel
    path, the reaper, and the worker's cancel-during-fork guard so there is one
    killpg call site with one error-reporting convention."""
    try:
        os.killpg(pgid, signal.SIGKILL)
        return True
    except OSError as exc:
        # pgid may have exited between a liveness check and this call.
        constants.err(f"job {job_id}: failed to kill pgid {pgid}: {exc}")
        return False


def _has_pgid_tracking(store, job_id, record):
    """True if a job still has ANY backend-pgid tracking — recorded in the
    record OR present as the crash-safe backend.pgid file — regardless of
    whether that pgid is currently alive. Gates the cancelled-orphan reap on
    *presence* (not liveness) so a dead-but-uncleared stale pgid is still
    cleaned up once, closing the recycled-pgid wrong-kill window."""
    if record.get("pgid") is not None:
        return True
    return os.path.exists(os.path.join(store.job_dir(job_id), BACKEND_PGID_FILENAME))


def _clear_pgid_tracking(store, job_id):
    """Erase all backend-pgid tracking for a job: null the recorded pgid (a
    terminal-safe mutate) and delete the crash-safe backend.pgid file. Called as
    the FINAL act of every site that kills a backend because the job went
    cancelled, so no later reap/status/list call can re-derive a stale pgid and
    SIGKILL a process group the kernel has since recycled."""

    def _clear(rec):
        return dict(rec, pgid=None)

    _clear.allow_terminal_reentry = True
    store.mutate(job_id, _clear)
    # constitution: exempt C-ERR — absent file is the expected steady state; nothing to recover
    with contextlib.suppress(OSError):
        os.remove(os.path.join(store.job_dir(job_id), BACKEND_PGID_FILENAME))


def _reap_cancelled_orphan(store, job_id, record):
    """Kill the orphaned backend group of a cancelled job (if still alive), then
    clear all pgid tracking so this runs at most once and no later pass can
    re-probe a (possibly recycled) pgid."""
    pgid = record.get("pgid") or _read_pgid_file(store.job_dir(job_id))
    if pgid and _backend_alive(store, job_id):
        _kill_pgid(store, job_id, pgid)
    _clear_pgid_tracking(store, job_id)


def _make_pgid_persister(store, job_id):
    """Return an on_pgid callback that records the backend's process group even
    after the job goes terminal (recording a pgid is bookkeeping, not a
    lifecycle transition), then kills the group if cancel already won the race."""

    def _record(rec):
        return dict(rec, pgid=_record.pgid_val)

    _record.allow_terminal_reentry = True

    def _persist(pgid_val):
        _record.pgid_val = pgid_val
        updated = store.mutate(job_id, _record)
        if updated.get("state") == "cancelled":
            # Detached (setsid) backend outlived the cancel; the worker is the
            # only party that reliably knows the pgid at this instant. Kill it,
            # then clear tracking so the pgid we just re-recorded cannot linger
            # stale for a later reap to re-probe.
            _kill_pgid(store, job_id, pgid_val)
            _clear_pgid_tracking(store, job_id)

    return _persist
