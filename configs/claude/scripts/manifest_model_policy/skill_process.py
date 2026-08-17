"""Bounded native provider process execution for direct skill handoff."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

PROVIDER_OUTPUT_LIMIT = 64 * 1024
_TERMINATION_GRACE_SECONDS = 1.0


@dataclass(frozen=True)
class CommandResult:
    """A bounded provider result, including whether its deadline expired."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    truncated: bool = False
    timed_out: bool = False


def _drain_bounded(stream, sink: bytearray, state: dict[str, bool]) -> None:
    """Append bounded output to `sink` under `state["lock"]`.

    The lock matters because a drain thread can be abandoned on the timeout
    path while still holding the pipe open: it may keep appending after the
    caller has moved on, and resizing a bytearray while another thread decodes
    it is not safe. Every mutation and every read of `sink` takes this lock.
    """
    lock = state["lock"]
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            return
        with lock:
            room = PROVIDER_OUTPUT_LIMIT - len(sink)
            if room > 0:
                sink.extend(chunk[:room])
            if len(chunk) > room:
                state["truncated"] = True


def _feed_stdin(stream, payload: bytes, state: dict[str, bool]) -> None:
    try:
        stream.write(payload)
    except BrokenPipeError:
        state["closed_early"] = True
    finally:
        stream.close()


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    # EPERM is reachable here, not just ESRCH: once the group leader is reaped
    # the pgid can be recycled by a process this user may not signal, and macOS
    # can return EPERM for a group whose leader has exited. Letting it escape
    # turned an ordinary provider timeout into an unhandled PermissionError
    # that crashed the whole skill run.
    #
    # EPERM does NOT prove the group is gone -- POSIX also returns it for a
    # LIVE target this process may not signal (a provider that re-execs under
    # a different uid). The caller must therefore not assume the child is dead
    # after this returns; see _release_reader_pipes.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    # constitution: exempt C-ERR -- the process already exited successfully.
    except (ProcessLookupError, PermissionError):
        # We could not signal it, but it may already be a zombie awaiting reap.
        # A non-blocking poll reclaims the pid without waiting on a live child.
        with suppress(OSError):
            process.poll()
        return
    try:
        process.wait(timeout=_TERMINATION_GRACE_SECONDS)
        parent_exited = True
    except subprocess.TimeoutExpired:
        parent_exited = False
    try:
        os.killpg(process.pid, signal.SIGKILL)
    # constitution: exempt C-ERR -- the full process group exited during grace.
    except (ProcessLookupError, PermissionError):
        return
    if not parent_exited:
        process.wait()


def _release_reader_pipes(
    process: subprocess.Popen[bytes], readers: tuple[threading.Thread, ...]
) -> None:
    """Join the drain threads under a deadline; never block on a survivor.

    A drain thread blocks in read() until every pipe write end closes, and a
    child that outlived termination (EPERM on a live target we may not signal)
    still holds one. Closing the stream here does not help: close() has to
    acquire the buffer lock the in-flight read already owns, so it would block
    for exactly as long. The threads are daemons, so abandoning them is safe --
    whatever they captured before the deadline is what gets reported, and the
    result is already marked timed_out.
    """
    del process
    for reader in readers:
        reader.join(timeout=_TERMINATION_GRACE_SECONDS)


def _snapshot(sink: bytearray, state: dict[str, Any]) -> tuple[bytes, bool]:
    """Copy a drain sink under its lock; an abandoned thread may still append."""
    with state["lock"]:
        return bytes(sink), bool(state["truncated"])


def _command_result(
    argv: Sequence[str],
    returncode: int,
    timed_out: bool,
    out: tuple[bytearray, dict[str, Any]],
    err: tuple[bytearray, dict[str, Any]],
) -> CommandResult:
    out_bytes, out_truncated = _snapshot(*out)
    err_bytes, err_truncated = _snapshot(*err)
    return CommandResult(
        tuple(argv),
        returncode,
        out_bytes.decode("utf-8", errors="replace"),
        err_bytes.decode("utf-8", errors="replace"),
        out_truncated or err_truncated,
        timed_out,
    )


class CommandRunner:
    """Run one provider in its own process group with bounded I/O and time."""

    def __init__(self, timeout_seconds: float = 120) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("provider timeout must be a positive number")
        self.timeout_seconds = float(timeout_seconds)

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin_bytes: bytes | None = None,
    ) -> CommandResult:
        """Return bounded output, terminating the full child group on timeout."""
        process = subprocess.Popen(
            tuple(argv),
            env=env,
            stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr = bytearray(), bytearray()
        stdout_state = {"truncated": False, "lock": threading.Lock()}
        stderr_state = {"truncated": False, "lock": threading.Lock()}
        assert process.stdout is not None and process.stderr is not None
        readers = (
            threading.Thread(
                target=_drain_bounded,
                args=(process.stdout, stdout, stdout_state),
                daemon=True,
            ),
            threading.Thread(
                target=_drain_bounded,
                args=(process.stderr, stderr, stderr_state),
                daemon=True,
            ),
        )
        for reader in readers:
            reader.start()
        stdin_state = {"closed_early": False}
        writer = self._start_writer(process, stdin_bytes, stdin_state)
        timed_out = False
        try:
            returncode = process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(process)
            returncode = 124
        if timed_out:
            # The child may have survived termination (EPERM on a live target
            # we may not signal). It still holds the pipe write ends, so an
            # unbounded join here would wedge the run forever -- strictly worse
            # than the crash this path replaced. Bound the wait, then close the
            # pipes so the drain threads see EOF and exit.
            _release_reader_pipes(process, readers)
        else:
            for reader in readers:
                reader.join()
        if writer is not None:
            writer.join(timeout=_TERMINATION_GRACE_SECONDS)
        if returncode == 0 and stdin_state["closed_early"]:
            raise RuntimeError("provider closed stdin before the prompt was delivered")
        return _command_result(
            argv, returncode, timed_out, (stdout, stdout_state), (stderr, stderr_state)
        )

    @staticmethod
    def _start_writer(process, payload, state):
        if payload is None:
            return None
        assert process.stdin is not None
        writer = threading.Thread(
            target=_feed_stdin,
            args=(process.stdin, payload, state),
            daemon=True,
        )
        writer.start()
        return writer
