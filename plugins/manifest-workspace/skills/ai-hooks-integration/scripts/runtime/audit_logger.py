#!/usr/bin/env python3
"""Append a bounded, redacted hook event to a safely opened JSONL audit log."""

import argparse
import json
import os
import re
import stat
import sys
import time

try:
    import fcntl
except ImportError:
    fcntl = None

MAX_INPUT = 65_536
MAX_RECORD = 16_384
ERROR = "audit logger failed"

_VALUE = (
    r"""(?:(?:\\\r?\n[ \t]*)|(?:\\[\s\S])|"(?:\\[\s\S]|[^"\\])*"|'[^']*'|[^\s'"\\])+"""
)
_PATTERNS = (
    re.compile(rf"(?i)(\bBearer\s+){_VALUE}"),
    re.compile(
        r"""(?i)(["']?--(?:password|token)["']?)(?:[ \t]*=|[ \t]+|\\\r?\n)[\s\S]*"""
    ),
    re.compile(r"(?is)(\b[A-Z0-9_]*_TOKEN\s*=\s*).+"),
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s]*@"),
)


def _redact(value):
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        redacted = []
        redact_next = False
        for item in value:
            if redact_next:
                redacted.append("[REDACTED]")
                redact_next = False
                continue
            if isinstance(item, str) and re.match(r"(?i)^--(?:password|token)=", item):
                flag, _secret = item.split("=", 1)
                redacted.append(flag + "=[REDACTED]")
                continue
            redacted.append(_redact(item))
            redact_next = isinstance(item, str) and item.lower() in (
                "--password",
                "--token",
            )
        return redacted
    if isinstance(value, str):
        text = value
        text = _PATTERNS[0].sub(r"\1[REDACTED]", text)
        text = _PATTERNS[1].sub(r"\1 [REDACTED]", text)
        text = _PATTERNS[2].sub(r"\1[REDACTED]", text)
        text = _PATTERNS[3].sub(r"\1[REDACTED]@", text)
        return text
    return value


def append(path: str, record: bytes) -> None:
    """Append a record under an exclusive lock and roll back short writes."""
    if fcntl is None:
        raise OSError
    parent_fd, leaf = _open_parent(path)
    fd = -1
    try:
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
        for attempt in range(3):
            try:
                fd = os.open(leaf, flags, 0o600, dir_fd=parent_fd)
                break
            except FileNotFoundError:
                if attempt == 2:
                    raise
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise OSError
        fcntl.flock(fd, fcntl.LOCK_EX)
        original_size = os.fstat(fd).st_size
        data = record + b"\n"
        try:
            written = os.write(fd, data)
            if written != len(data):
                raise OSError("short append")
        except OSError:
            os.ftruncate(fd, original_size)
            raise
    finally:
        if fd >= 0:
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        os.close(parent_fd)


def main() -> int:
    """Validate and append one redacted event from standard input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=os.environ.get("AI_HOOK_AUDIT_LOG"))
    args = parser.parse_args()
    if not args.path:
        print(ERROR, file=sys.stderr)
        return 1
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError
        event = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        if not isinstance(event, dict):
            raise ValueError
        record_obj = {"timestamp": time.time(), "event": _redact(event)}
        record = json.dumps(
            record_obj, ensure_ascii=True, allow_nan=False, separators=(",", ":")
        ).encode("ascii")
        if len(record) + 1 > MAX_RECORD:
            raise ValueError
        append(args.path, record)
        return 0
    # constitution: exempt C-ERR — generic diagnostics avoid disclosing secrets or filesystem paths.
    except Exception:
        print(ERROR, file=sys.stderr)
        return 1


def _open_parent(path):
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    parts = path.split(os.sep)
    if any(part in ("", ".", "..") for part in parts[1:-1]) or not parts[-1]:
        raise OSError
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise OSError
    fd = os.open(os.sep, flags)
    try:
        for component in parts[1:-1]:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise OSError
        return fd, parts[-1]
    # constitution: exempt C-ERR — close this descriptor even during cancellation before propagating.
    except BaseException:
        os.close(fd)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
