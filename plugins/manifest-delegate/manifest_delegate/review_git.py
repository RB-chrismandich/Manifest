"""Fail-closed, bounded Git capture for review and Stop-gate observations."""

import contextlib
import os
import selectors
import signal
import subprocess
import time

from .backend import TASK_LIMIT
from .process_capture import MAX_FAILURE_STREAM_BYTES

GIT_TIMEOUT_SECONDS = 30


class ReviewDiffError(Exception):
    """Git could not produce complete review evidence within its limits."""


def _collect(
    proc: subprocess.Popen[bytes], max_bytes: int, deadline: float
) -> tuple[bytes, bytes]:
    buffers = [bytearray(), bytearray()]
    caps = [max_bytes, MAX_FAILURE_STREAM_BYTES]
    assert proc.stdout is not None and proc.stderr is not None
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ, 0)
        selector.register(proc.stderr, selectors.EVENT_READ, 1)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReviewDiffError("git review collection time limit exceeded")
            for key, _ in selector.select(remaining):
                index = key.data
                room = caps[index] - len(buffers[index])
                chunk = os.read(key.fd, min(65536, room + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if len(chunk) > room:
                    stream = "stdout" if index == 0 else "stderr"
                    raise ReviewDiffError(f"git review {stream} byte limit exceeded")
                buffers[index].extend(chunk)
    return bytes(buffers[0]), bytes(buffers[1])


def capture_git(
    args: list[str],
    cwd: str | os.PathLike[str] | None,
    *,
    max_bytes: int = TASK_LIMIT,
    deadline: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Capture both pipes without truncation; kill the group on limit/error.

    The deadline includes draining inherited pipes and waiting for exit. The
    caller interprets exit codes: no-index diffs accept 1, ref/status probes do not.
    """
    deadline = (
        deadline if deadline is not None else time.monotonic() + GIT_TIMEOUT_SECONDS
    )
    if max_bytes < 0 or time.monotonic() >= deadline:
        raise ReviewDiffError("git review collection limit exceeded")
    argv = ["git", *args]
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise ReviewDiffError(f"git failed to launch: {exc}") from exc
    try:
        stdout, stderr = _collect(proc, max_bytes, deadline)
        proc.wait(timeout=max(0, deadline - time.monotonic()))
        return subprocess.CompletedProcess(
            argv, proc.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")
        )
    except subprocess.TimeoutExpired as exc:
        raise ReviewDiffError("git review collection time limit exceeded") from exc
    except (OSError, UnicodeError) as exc:
        raise ReviewDiffError(f"could not read git review output: {exc}") from exc
    finally:
        # Also terminate children that inherited pipes after Git itself exited.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        assert proc.stdout is not None and proc.stderr is not None
        proc.stdout.close()
        proc.stderr.close()
        proc.wait()
