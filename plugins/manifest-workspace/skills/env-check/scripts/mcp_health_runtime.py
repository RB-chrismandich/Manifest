"""Bounded subprocess, clock, JSON, and file-state helpers for MCP health."""

from __future__ import annotations

import fcntl
import json
import os
import selectors
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_OUTPUT_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    outcome: str
    output: str = ""
    returncode: int | None = None


Runner = Callable[[Sequence[str], float, Mapping[str, str]], CommandResult]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_json_object(
    path: Path,
    *,
    required: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_OUTPUT_BYTES + 1)
    except FileNotFoundError:
        return None, "unavailable" if required else None
    except OSError:
        return None, "unavailable"
    if len(payload) > MAX_OUTPUT_BYTES:
        return None, "unparseable"
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None, "unparseable"
    if not isinstance(value, dict):
        return None, "unparseable"
    return value, None


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        with suppress(ProcessLookupError):
            process.kill()
    with suppress(subprocess.TimeoutExpired, ChildProcessError):
        process.wait(timeout=1)


def _drain_output(
    process: subprocess.Popen[bytes],
    selector: selectors.BaseSelector,
    deadline: float,
    output: bytearray,
    monotonic: Callable[[], float],
) -> str | None:
    """Read the child pipe until EOF; return the early-outcome name or None."""
    eof = False
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return "timeout"
        events = selector.select(min(remaining, 0.1))
        for key, _mask in events:
            try:
                chunk = os.read(
                    key.fd,
                    min(65536, MAX_OUTPUT_BYTES + 1 - len(output)),
                )
            except BlockingIOError:
                continue
            if not chunk:
                eof = True
                with suppress(KeyError):
                    selector.unregister(key.fd)
                continue
            output.extend(chunk)
            if len(output) > MAX_OUTPUT_BYTES:
                return "overflow"
        if process.poll() is not None and eof:
            break
    return None


def run_bounded(
    argv: Sequence[str],
    timeout_seconds: float,
    environment: Mapping[str, str],
    *,
    popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    monotonic: Callable[[], float] = time.monotonic,
) -> CommandResult:
    """Run argv in a new process group while retaining at most 1 MiB output."""
    try:
        process = popen_factory(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(environment),
            start_new_session=True,
        )
    except (FileNotFoundError, PermissionError, OSError):
        return CommandResult("unavailable")

    if process.stdout is None:
        _kill_process_group(process)
        return CommandResult("unavailable")

    deadline = monotonic() + timeout_seconds
    output = bytearray()
    selector = selectors.DefaultSelector()
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector.register(descriptor, selectors.EVENT_READ)
    try:
        outcome = _drain_output(process, selector, deadline, output, monotonic)
        if outcome is not None:
            _kill_process_group(process)
            return CommandResult(outcome)
        returncode = process.wait(timeout=max(0.01, deadline - monotonic()))
    except (OSError, subprocess.SubprocessError):
        _kill_process_group(process)
        return CommandResult("unavailable")
    finally:
        selector.close()
        process.stdout.close()

    try:
        decoded = output.decode("utf-8")
    except UnicodeDecodeError:
        return CommandResult("unparseable", returncode=returncode)
    return CommandResult("completed", decoded, returncode)


def _prepare_state_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _try_probe_lock(state_dir: Path, harness: str) -> tuple[int | None, bool]:
    descriptor: int | None = None
    try:
        _prepare_state_dir(state_dir)
        descriptor = os.open(
            state_dir / f"mcp-{harness}.lock",
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return descriptor, False
        return descriptor, True
    except OSError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        return None, False


def _release_probe_lock(descriptor: int | None) -> None:
    if descriptor is None:
        return
    with suppress(OSError):
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)


def _atomic_write_report(path: Path, report: Mapping[str, Any]) -> bool:
    temporary_name: str | None = None
    try:
        _prepare_state_dir(path.parent)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False
    finally:
        if temporary_name is not None:
            with suppress(OSError):
                os.unlink(temporary_name)
