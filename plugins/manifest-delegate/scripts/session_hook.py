#!/usr/bin/env python3
# help-coverage: covered by tests/bats/help_coverage.bats
"""SessionStart/SessionEnd thin wrapper for manifest-delegate.

SessionStart: records session_id + transcript_path for later transfer
lookups. SessionEnd: reaps orphaned gate/job records — jobs left
non-terminal whose recorded backend process group is no longer alive.
"""

import sys

# --- Early interpreter version probe (D11) --------------------------------
if sys.version_info < (3, 9):  # noqa: UP036 — deliberate runtime guard, see D11
    sys.stderr.write(
        "session_hook.py: unsupported Python version %s.%s — "  # noqa: UP031
        "manifest-delegate requires Python 3.9 or newer.\n"
        "Install a supported interpreter, e.g.:\n"
        "  macOS:  brew install python@3.11\n"
        "  Linux:  use your distro's python3.9+ package\n"
        "Then re-run with that interpreter's `python3` on PATH.\n"
        % (sys.version_info[0], sys.version_info[1])
    )
    sys.exit(2)

import argparse
import contextlib
import fcntl
import json
import os
import stat
import sys as _sys
import tempfile
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPT_DIR)
import delegate  # noqa: E402


def _load_sessions():
    if not os.path.exists(delegate.SESSIONS_CAPTURE_FILE):
        return {}
    try:
        return json.load(open(delegate.SESSIONS_CAPTURE_FILE))
    except ValueError:
        return {}


def _mutate_sessions(mutate):
    """Apply `mutate` to the capture dict under an inter-process flock.

    Concurrent SessionStart/SessionEnd hooks (parallel harness sessions are
    supported) must not lose each other's writes, so load+mutate+atomic-replace
    all happen inside the lock; the temp file is unique (mkstemp) and fsync'd
    before the rename so a crash cannot leave a torn file.
    """
    path = delegate.SESSIONS_CAPTURE_FILE
    dest_dir = os.path.dirname(path)
    os.makedirs(dest_dir, exist_ok=True)
    lock_fd = os.open(path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        sessions = _load_sessions()
        mutate(sessions)
        fd, tmp = tempfile.mkstemp(dir=dest_dir, prefix=".sessions.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(sessions, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(tmp, path)
        except OSError:
            # constitution: exempt C-ERR — cleanup of a temp we are already failing on; nothing to recover
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _capture_session(session_id, entry):
    """Record one session's transcript location."""
    _mutate_sessions(lambda sessions: sessions.__setitem__(session_id, entry))


def _forget_session(session_id):
    """Drop one session's capture entry. Idempotent."""
    _mutate_sessions(lambda sessions: sessions.pop(session_id, None))


def handle_session_start(payload):
    session_id = payload.get("session_id")
    if not session_id:
        return 0
    entry = {
        "transcript_path": payload.get("transcript_path"),
        "cwd": payload.get("cwd"),
        # Recorded so an operator can tell stale entries apart. Deliberately
        # NOT used to break a tie between two live sessions in one workspace:
        # transfer refuses instead (see delegate._resolve_transfer_source).
        "captured_at": time.time(),
    }
    try:
        _capture_session(session_id, entry)
    except OSError as exc:
        # SessionStart's contract is to always exit 0; a capture I/O failure
        # must not crash the hook. Report and continue.
        _sys.stderr.write(
            f"session_hook: failed to capture session {session_id}: {exc}\n"
        )
    return 0


def handle_session_end(payload):
    """Drop this session's capture entry, then reap its orphaned jobs.

    The capture entry must go first and unconditionally: while it lingers, a
    `delegate transfer` run from the same worktree sees two candidate sessions
    and refuses (or, before that refusal existed, silently imported the wrong
    transcript). Eviction is what keeps the common single-live-session case
    working without --source.

    Job reaping delegates entirely to delegate.JobStore.reap_if_dead, the
    dispatcher's own locked reaper, so state vocabulary (TERMINAL_STATES/
    NON_TERMINAL_STATES) and pgid-liveness semantics (EPERM == alive) stay in
    exactly one place instead of being duplicated here.
    """
    session_id = payload.get("session_id")
    if session_id:
        try:
            _forget_session(session_id)
        except OSError as exc:
            # SessionEnd must still exit 0; a stale entry degrades transfer to
            # "pass --source", it does not break the session.
            _sys.stderr.write(
                f"session_hook: failed to forget session {session_id}: {exc}\n"
            )

    store = delegate.JobStore(cwd=payload.get("cwd"))
    for job_id in store.list_job_ids():
        try:
            store.reap_if_dead(job_id)
        except (OSError, ValueError):
            continue
    return 0


def main(argv=None):
    # type: (list[str] | None) -> int
    """Dispatch a SessionStart/SessionEnd hook payload to its handler.

    Reads the hook JSON from stdin (or --stdin-json for tests), routes on
    `hook_event_name`, and always returns 0 — a hook must never block the
    session it is attached to.
    """
    parser = argparse.ArgumentParser(
        prog="session_hook.py",
        description="SessionStart/SessionEnd wrapper: session tracking + orphan job reap.",
    )
    parser.add_argument(
        "--stdin-json",
        metavar="FILE",
        default=None,
        help="read hook payload from FILE instead of stdin (testing)",
    )
    args = parser.parse_args(argv)

    if args.stdin_json:
        with open(args.stdin_json, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    event = payload.get("hook_event_name")
    if event == "SessionStart":
        return handle_session_start(payload)
    if event == "SessionEnd":
        return handle_session_end(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
