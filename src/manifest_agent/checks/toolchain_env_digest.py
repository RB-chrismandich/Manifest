"""Deterministic, fail-closed environment-tree attestation."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path

from .toolchain_pth import canonical_pth_bytes


def distribution_set_digest(
    env_root: Path,
    kind: str,
    *,
    store: Path | None = None,
    checkout_root: Path | None = None,
    canonical_env_root: Path | None = None,
) -> str:
    """Return a framed digest of the complete materialized environment tree."""
    if kind not in {"python-env", "node-env"}:
        raise ValueError(f"distribution_set_digest: unknown env kind {kind!r}")
    root = env_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("environment root is not a directory")
    canonical_root = canonical_env_root or root
    hasher = hashlib.sha256()
    _attest_tree(root, root, canonical_root, hasher, store, checkout_root)
    return hasher.hexdigest()


def _frame(hasher, kind: bytes, relative: str, payload: bytes = b"") -> None:
    encoded = relative.encode("utf-8", "surrogateescape")
    hasher.update(kind)
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _attest_tree(
    root: Path,
    directory: Path,
    canonical_root: Path,
    hasher,
    store: Path | None,
    checkout_root: Path | None,
) -> None:
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        path = Path(entry.path)
        relative = path.relative_to(root).as_posix()
        mode = entry.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            _frame(hasher, b"D", relative, (mode & 0o777).to_bytes(2, "big"))
            _attest_tree(root, path, canonical_root, hasher, store, checkout_root)
        elif stat.S_ISREG(mode):
            _attest_regular_file(
                root, canonical_root, path, relative, mode, hasher, store, checkout_root
            )
        elif stat.S_ISLNK(mode):
            _attest_symlink(root, path, relative, hasher)
        else:
            raise ValueError(f"special environment file: {relative}")


def _attest_regular_file(
    root: Path,
    canonical_root: Path,
    path: Path,
    relative: str,
    mode: int,
    hasher,
    store: Path | None,
    checkout_root: Path | None,
) -> None:
    stat_result = path.stat(follow_symlinks=False)
    if stat_result.st_nlink != 1:
        raise ValueError(f"hardlinked environment file: {relative}")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        content = stream.read()
    content = _canonical_file_bytes(
        root, canonical_root, path, relative, content, store, checkout_root
    )
    encoded = relative.encode("utf-8", "surrogateescape")
    hasher.update(b"F")
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)
    hasher.update((2 + len(content)).to_bytes(8, "big"))
    hasher.update((mode & 0o777).to_bytes(2, "big"))
    hasher.update(content)


def _canonical_file_bytes(
    root: Path,
    canonical_root: Path,
    path: Path,
    relative: str,
    content: bytes,
    store: Path | None,
    checkout_root: Path | None,
) -> bytes:
    if relative.endswith(".dist-info/RECORD"):
        return _canonical_record_bytes(
            root, canonical_root, path, relative, content, store, checkout_root
        )
    return _normalized_generated_path_bearers(
        root, canonical_root, path, relative, content, store, checkout_root
    )


def _canonical_record_bytes(
    root: Path,
    canonical_root: Path,
    record_path: Path,
    record_relative: str,
    content: bytes,
    store: Path | None,
    checkout_root: Path | None,
) -> bytes:
    try:
        text = content.decode("utf-8", "surrogateescape")
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as error:
        raise ValueError(f"malformed RECORD: {record_relative}") from error
    rendered: list[list[str]] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) < 3 or not row[0]:
            raise ValueError(f"malformed RECORD: {record_relative}")
        target_relative = _safe_record_path(row[0], record_relative)
        if target_relative in seen:
            raise ValueError(f"duplicate RECORD path: {target_relative}")
        seen.add(target_relative)
        digest, size = row[1], row[2]
        if target_relative == record_relative:
            if digest or size:
                raise ValueError(f"self-hashed RECORD: {record_relative}")
            rendered.append(row)
            continue
        if not digest or not size or not digest.startswith("sha256="):
            raise ValueError(f"untrusted RECORD hash: {target_relative}")
        encoded_digest = digest.removeprefix("sha256=")
        try:
            decoded_digest = base64.b64decode(
                encoded_digest + "=" * (-len(encoded_digest) % 4),
                altchars=b"-_",
                validate=True,
            )
            if len(decoded_digest) != 32:
                raise ValueError
            int(size)
        except ValueError as error:
            raise ValueError(f"malformed RECORD metadata: {target_relative}") from error
        canonical = _canonical_record_target(
            root, canonical_root, target_relative, store, checkout_root
        )
        row[1] = "sha256=" + base64.urlsafe_b64encode(
            hashlib.sha256(canonical).digest()
        ).rstrip(b"=").decode("ascii")
        row[2] = str(len(canonical))
        rendered.append(row)
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rendered)
    return output.getvalue().encode("utf-8", "surrogateescape")


def _canonical_record_target(
    root: Path,
    canonical_root: Path,
    target_relative: str,
    store: Path | None,
    checkout_root: Path | None,
) -> bytes:
    target = root / target_relative
    try:
        target_stat = target.lstat()
    except OSError as error:
        raise ValueError(f"missing RECORD target: {target_relative}") from error
    if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_nlink != 1:
        raise ValueError(f"unsafe RECORD target: {target_relative}")
    with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        target_bytes = stream.read()
    return _normalized_generated_path_bearers(
        root,
        canonical_root,
        target,
        target_relative,
        target_bytes,
        store,
        checkout_root,
    )


def _safe_record_path(value: str, record_relative: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe RECORD path: {value!r}")
    relative = path.as_posix()
    if relative != record_relative and relative.endswith("/RECORD"):
        raise ValueError(f"nested RECORD target: {relative}")
    return relative


def _canonical_pyvenv_bytes(content: bytes, env_root: Path) -> bytes:
    provider = Path(sys.executable).resolve(strict=True)
    provider_home = provider.parent
    canonical_lines: list[bytes] = []
    for raw_line in content.splitlines():
        key, separator, raw_value = raw_line.partition(b" = ")
        if key not in {b"home", b"executable", b"command"}:
            canonical_lines.append(raw_line)
            continue
        if not separator:
            raise ValueError("malformed pyvenv metadata")
        value = raw_value.decode("utf-8", "surrogateescape")
        if key == b"command":
            canonical_lines.append(
                b"command = " + _canonical_pyvenv_command(value, provider, env_root)
            )
            continue
        try:
            resolved = Path(value).resolve(strict=True)
        except OSError as error:
            raise ValueError(f"untrusted pyvenv {key.decode()}") from error
        if key == b"home":
            if resolved != provider_home:
                raise ValueError("untrusted pyvenv home")
            canonical_lines.append(b"home = <PYTHON_HOME>")
        elif resolved != provider:
            raise ValueError("untrusted pyvenv executable")
        else:
            canonical_lines.append(b"executable = <PYTHON>")
    return b"\n".join(canonical_lines) + b"\n"


def _canonical_pyvenv_command(value: str, provider: Path, env_root: Path) -> bytes:
    try:
        tokens = shlex.split(value)
    except ValueError as error:
        raise ValueError("malformed pyvenv command") from error
    if len(tokens) < 4 or tokens[1:3] != ["-m", "venv"]:
        raise ValueError("untrusted pyvenv command")
    canonical: list[str] = []
    output_seen = False
    for token in tokens:
        if not Path(token).is_absolute():
            canonical.append(token)
            continue
        resolved = Path(token).resolve(strict=False)
        if resolved == provider:
            canonical.append("<PYTHON>")
        elif resolved == env_root.resolve(strict=True):
            canonical.append("<ENV>")
            output_seen = True
        else:
            raise ValueError("untrusted pyvenv command")
    if canonical[0] != "<PYTHON>" or not output_seen:
        raise ValueError("untrusted pyvenv command")
    return shlex.join(canonical).encode("utf-8", "surrogateescape")


def _normalized_generated_path_bearers(
    env_root: Path,
    root: Path,
    path: Path,
    relative: str,
    content: bytes,
    store: Path | None,
    checkout_root: Path | None,
) -> bytes:
    """Normalize only structurally known generated path-bearing fields."""
    if relative.endswith(".pth"):
        return canonical_pth_bytes(path, env_root)
    if relative == "pyvenv.cfg":
        return _canonical_pyvenv_bytes(content, env_root)
    if relative.endswith("direct_url.json"):
        try:
            document = json.loads(content)
            url = document.get("url")
            if isinstance(url, str) and url.startswith("file://") and checkout_root:
                candidate = Path(url.removeprefix("file://"))
                if candidate.is_relative_to(checkout_root):
                    document["url"] = (
                        f"file://<CHECKOUT>/{candidate.relative_to(checkout_root)}"
                    )
                    return json.dumps(
                        document, sort_keys=True, separators=(",", ":")
                    ).encode()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return content
    if relative.endswith("uv_cache.json"):
        try:
            document = json.loads(content)
            return json.dumps(
                _normalize_json_paths(document, root, checkout_root),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return content
    if relative.startswith("bin/activate"):
        return content.replace(os.fsencode(root), b"<ENV>")
    trampoline = b"'''exec' '" + os.fsencode(root / "bin" / "python")
    if content.startswith(b"#!/bin/sh\n" + trampoline):
        return content.replace(trampoline, b"'''exec' '<ENV>/bin/python", 1)
    if not relative.startswith("bin/") or not content.startswith(b"#!"):
        return content
    prefix = b"#!" + os.fsencode(root / "bin" / "python")
    if not content.startswith(prefix):
        return content
    suffix = content[len(prefix) : len(prefix) + 1]
    if suffix not in {b"", b"\n", b" ", b"\t"}:
        return content
    return b"#!<ENV>/bin/python" + content[len(prefix) :]


def _normalize_json_paths(value, root: Path, checkout_root: Path | None):
    if isinstance(value, str):
        for prefix, marker in ((root, "<ENV>"), (checkout_root, "<CHECKOUT>")):
            if prefix and value.startswith(str(prefix)):
                return marker + value[len(str(prefix)) :]
        return value
    if isinstance(value, list):
        return [_normalize_json_paths(item, root, checkout_root) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_json_paths(item, root, checkout_root)
            for key, item in value.items()
        }
    return value


def external_python_identity(path: Path) -> bytes:
    """Return the trusted running provider's stable byte and mode identity."""
    resolved = path.resolve(strict=True)
    provider = Path(sys.executable).resolve(strict=True)
    info = resolved.stat()
    if (
        resolved != provider
        or not resolved.name.startswith("python")
        or not os.access(resolved, os.X_OK)
    ):
        raise ValueError("environment interpreter is not the trusted Python provider")
    with open(resolved, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return f"python-provider:{info.st_mode & 0o777}:{digest}".encode()


def is_python_launcher_role(relative: str) -> bool:
    """Whether a path is the environment's attested `bin/python*` role."""
    path = Path(relative)
    return (
        len(path.parts) == 2
        and path.parts[0] == "bin"
        and re.fullmatch(r"python(?:\d+(?:\.\d+)?)?", path.name) is not None
    )


def _attest_symlink(root: Path, path: Path, relative: str, hasher) -> None:
    target = os.readlink(path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"broken environment symlink: {relative}") from error
    if not resolved.is_relative_to(root):
        if not is_python_launcher_role(relative):
            raise ValueError(f"environment symlink escapes root: {relative}")
        _frame(hasher, b"L", relative, external_python_identity(path))
        return
    _frame(hasher, b"L", relative, target.encode("utf-8", "surrogateescape"))
