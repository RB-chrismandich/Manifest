"""Deterministic, fail-closed environment-tree attestation."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import platform
import re
import shlex
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .toolchain_pth import canonical_pth_bytes


@dataclass(frozen=True)
class ExternalPythonProvider:
    """An executable Python provider observed outside a materialized venv."""

    implementation: str
    version: str
    build: str
    exe_sha256: str

    def lock_record(self) -> dict[str, str]:
        """Return the exact lock record required to reuse this provider."""
        return {
            "implementation": self.implementation,
            "version": self.version,
            "build": self.build,
            "exe_sha256": self.exe_sha256,
        }

    def matches(self, pinned: object) -> bool:
        """Whether a lock pin exactly attests this external provider."""
        return isinstance(pinned, dict) and pinned == self.lock_record()


def trusted_python_provider() -> ExternalPythonProvider:
    """Describe the already-running interpreter without executing a provider."""
    executable = Path(sys.executable).resolve(strict=True)
    info = executable.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(executable, os.X_OK):
        raise ValueError("running Python provider is not executable")
    with open(executable, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return ExternalPythonProvider(
        implementation=sys.implementation.name,
        version=".".join(map(str, sys.version_info[:3])),
        build=":".join(platform.python_build()),
        exe_sha256=digest,
    )


def external_python_provider(path: Path) -> ExternalPythonProvider:
    """Return the identity of the sole provider trusted before materialization."""
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError("environment interpreter is not executable") from error
    if resolved != Path(sys.executable).resolve(strict=True):
        raise ValueError("environment interpreter is not the trusted Python provider")
    return trusted_python_provider()


def python_provider_from_env(env_root: Path) -> Path:
    """Return an environment's launcher only when it is this process's provider."""
    try:
        provider = (env_root / "bin" / "python").resolve(strict=True)
    except OSError as error:
        raise ValueError("environment lacks a trusted Python provider") from error
    if provider != Path(sys.executable).resolve(strict=True):
        raise ValueError("environment interpreter is not the trusted Python provider")
    return provider


@dataclass(frozen=True)
class _DigestContext:
    """The immutable environment locations that every digest operation shares."""

    root: Path
    canonical_root: Path
    store: Path | None
    checkout_root: Path | None
    python_provider: dict[str, str] | None


def distribution_set_digest(
    env_root: Path,
    kind: str,
    *,
    store: Path | None = None,
    checkout_root: Path | None = None,
    canonical_env_root: Path | None = None,
    python_provider: dict[str, str] | None = None,
) -> str:
    """Return a framed digest of the complete materialized environment tree."""
    if kind not in {"python-env", "node-env"}:
        raise ValueError(f"distribution_set_digest: unknown env kind {kind!r}")
    root = env_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("environment root is not a directory")
    context = _DigestContext(
        root, canonical_env_root or root, store, checkout_root, python_provider
    )
    hasher = hashlib.sha256()
    _attest_tree(context, root, hasher)
    return hasher.hexdigest()


def _frame(hasher, kind: bytes, relative: str, payload: bytes = b"") -> None:
    encoded = relative.encode("utf-8", "surrogateescape")
    hasher.update(kind)
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _attest_tree(context: _DigestContext, directory: Path, hasher) -> None:
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        path = Path(entry.path)
        relative = path.relative_to(context.root).as_posix()
        mode = entry.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            _frame(hasher, b"D", relative, (mode & 0o777).to_bytes(2, "big"))
            _attest_tree(context, path, hasher)
        elif stat.S_ISREG(mode):
            _attest_regular_file(context, path, relative, mode, hasher)
        elif stat.S_ISLNK(mode):
            _attest_symlink(context, path, relative, hasher)
        else:
            raise ValueError(f"special environment file: {relative}")


def _attest_regular_file(
    context: _DigestContext, path: Path, relative: str, mode: int, hasher
) -> None:
    stat_result = path.stat(follow_symlinks=False)
    if stat_result.st_nlink != 1:
        raise ValueError(f"hardlinked environment file: {relative}")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        content = stream.read()
    content = _canonical_file_bytes(context, path, relative, content)
    encoded = relative.encode("utf-8", "surrogateescape")
    hasher.update(b"F")
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)
    hasher.update((2 + len(content)).to_bytes(8, "big"))
    hasher.update((mode & 0o777).to_bytes(2, "big"))
    hasher.update(content)


def _canonical_file_bytes(
    context: _DigestContext, path: Path, relative: str, content: bytes
) -> bytes:
    if relative.endswith(".dist-info/RECORD"):
        return _canonical_record_bytes(context, path, relative, content)
    return _normalized_generated_path_bearers(context, path, relative, content)


def _record_rows(content: bytes, record_relative: str) -> list[list[str]]:
    try:
        text = content.decode("utf-8", "surrogateescape")
        return list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        raise ValueError(f"malformed RECORD: {record_relative}") from error


def _canonical_record_bytes(
    context: _DigestContext, record_path: Path, record_relative: str, content: bytes
) -> bytes:
    """Canonicalize RECORD metadata while validating each owned target."""
    rendered: list[list[str]] = []
    seen: set[str] = set()
    for row in _record_rows(content, record_relative):
        rendered.append(
            _canonical_record_row(context, record_path, record_relative, row, seen)
        )
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rendered)
    return output.getvalue().encode("utf-8", "surrogateescape")


def _canonical_record_row(
    context: _DigestContext,
    record_path: Path,
    record_relative: str,
    row: list[str],
    seen: set[str],
) -> list[str]:
    if len(row) != 3 or not row[0]:
        raise ValueError(f"malformed RECORD: {record_relative}")
    target, target_relative = _record_target_path(context.root, record_path, row[0])
    if target_relative in seen:
        raise ValueError(f"duplicate RECORD path: {target_relative}")
    seen.add(target_relative)
    if target_relative == record_relative:
        if row[1] or row[2]:
            raise ValueError(f"self-hashed RECORD: {record_relative}")
        return ["RECORD", "", ""]
    _validate_record_metadata(row[1], row[2], target_relative)
    canonical = _canonical_record_target(context, target, target_relative)
    canonical_row = os.path.relpath(target, record_path.parent.parent).replace(
        os.sep, "/"
    )
    digest = base64.urlsafe_b64encode(hashlib.sha256(canonical).digest()).rstrip(b"=")
    return [canonical_row, f"sha256={digest.decode('ascii')}", str(len(canonical))]


def _validate_record_metadata(digest: str, size: str, target_relative: str) -> None:
    if bool(digest) != bool(size):
        raise ValueError(f"malformed RECORD metadata: {target_relative}")
    if not digest:
        return
    if not digest.startswith("sha256="):
        raise ValueError(f"untrusted RECORD hash: {target_relative}")
    try:
        value = digest.removeprefix("sha256=")
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        if len(decoded) != 32 or int(size) < 0:
            raise ValueError
    except ValueError as error:
        raise ValueError(f"malformed RECORD metadata: {target_relative}") from error


def _record_target_path(root: Path, record_path: Path, value: str) -> tuple[Path, str]:
    """Resolve a PyPA RECORD row from its containing site-packages directory."""
    path = Path(value)
    if path.is_absolute() or not path.parts:
        raise ValueError(f"unsafe RECORD path: {value!r}")
    try:
        target = (record_path.parent.parent / path).resolve(strict=False)
        target_relative = target.relative_to(root).as_posix()
    except (OSError, ValueError) as error:
        raise ValueError(f"unsafe RECORD path: {value!r}") from error
    return target, target_relative


def _canonical_record_target(
    context: _DigestContext, target: Path, target_relative: str
) -> bytes:
    try:
        target_stat = target.lstat()
    except OSError as error:
        raise ValueError(f"missing RECORD target: {target_relative}") from error
    if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_nlink != 1:
        raise ValueError(f"unsafe RECORD target: {target_relative}")
    with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        target_bytes = stream.read()
    return _normalized_generated_path_bearers(
        context, target, target_relative, target_bytes
    )


def _trusted_provider_for_context(
    python_provider: dict[str, str] | None,
) -> tuple[ExternalPythonProvider, Path]:
    provider = trusted_python_provider()
    if python_provider is not None and not provider.matches(python_provider):
        raise ValueError("Python provider does not match pinned provider")
    return provider, Path(sys.executable).resolve(strict=True)


def _canonical_pyvenv_bytes(
    content: bytes, env_root: Path, python_provider: dict[str, str] | None
) -> bytes:
    """Bind uv's generated metadata to the pre-authenticated provider."""
    values = {
        key: value
        for line in content.decode("utf-8", "surrogateescape").splitlines()
        if (key := line.partition(" = ")[0]) and (value := line.partition(" = ")[2])
    }
    _provider, executable = _trusted_provider_for_context(python_provider)
    try:
        launcher = python_provider_from_env(env_root)
        provider_home = Path(values["home"]).resolve(strict=True)
        base_prefix = Path(sys.base_prefix).resolve(strict=True)
    except (KeyError, OSError) as error:
        raise ValueError("untrusted pyvenv metadata") from error
    if launcher != executable or provider_home not in {
        base_prefix,
        base_prefix / "bin",
    }:
        raise ValueError("untrusted pyvenv home")
    try:
        configured_executable = (
            Path(values["executable"]).resolve(strict=True)
            if "executable" in values
            else executable
        )
    except OSError as error:
        raise ValueError("untrusted pyvenv executable") from error
    if configured_executable != executable:
        raise ValueError("untrusted pyvenv executable")
    if "command" in values:
        _canonical_pyvenv_command(values["command"], executable, env_root)
    canonical_lines: list[bytes] = []
    for raw_line in content.splitlines():
        key, separator, _raw_value = raw_line.partition(b" = ")
        if key not in {b"home", b"executable", b"command"}:
            canonical_lines.append(raw_line)
        elif not separator:
            raise ValueError("malformed pyvenv metadata")
        elif key == b"home":
            canonical_lines.append(b"home = <PYTHON_HOME>")
        elif key == b"executable":
            canonical_lines.append(b"executable = <PYTHON>")
        else:
            canonical_lines.append(b"command = <PYTHON_COMMAND>")
    return b"\n".join(canonical_lines) + b"\n"


def _canonical_pyvenv_command(value: str, provider: Path, env_root: Path) -> None:
    try:
        tokens = shlex.split(value)
    except ValueError as error:
        raise ValueError("malformed pyvenv command") from error
    if not tokens or Path(tokens[0]).resolve(strict=False) != provider:
        raise ValueError("untrusted pyvenv command")
    if not any(
        Path(token).resolve(strict=False) == env_root.resolve(strict=True)
        for token in tokens[1:]
        if Path(token).is_absolute()
    ):
        raise ValueError("untrusted pyvenv command")


def _normalized_generated_path_bearers(
    context: _DigestContext, path: Path, relative: str, content: bytes
) -> bytes:
    """Normalize only structurally known generated path-bearing fields."""
    env_root = context.root
    root = context.canonical_root
    checkout_root = context.checkout_root
    if relative.endswith(".pth"):
        return canonical_pth_bytes(path, env_root)
    if relative == "pyvenv.cfg":
        return _canonical_pyvenv_bytes(content, env_root, context.python_provider)
    if relative.endswith("direct_url.json"):
        try:
            document = json.loads(content)
            url = document.get("url")
            if (
                isinstance(url, str)
                and url.startswith("file://")
                and checkout_root
                and (candidate := Path(url.removeprefix("file://"))).is_relative_to(
                    checkout_root
                )
            ):
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
                _normalize_uv_cache_metadata(
                    _normalize_json_paths(document, root, checkout_root)
                ),
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


def _normalize_uv_cache_metadata(value):
    if isinstance(value, dict):
        if set(value) == {"secs_since_epoch", "nanos_since_epoch"} and all(
            isinstance(item, int) for item in value.values()
        ):
            return {"secs_since_epoch": 0, "nanos_since_epoch": 0}
        return {key: _normalize_uv_cache_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_uv_cache_metadata(item) for item in value]
    return value


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


def external_python_identity(path: Path, pinned: dict[str, str] | None = None) -> bytes:
    """Return a provider identity only when it is ambient-trusted or pinned."""
    resolved = path.resolve(strict=True)
    if pinned is None and resolved != Path(sys.executable).resolve(strict=True):
        raise ValueError("environment interpreter is not the trusted Python provider")
    provider = external_python_provider(path)
    if pinned is not None and not provider.matches(pinned):
        raise ValueError("environment interpreter does not match pinned provider")
    return json.dumps(
        provider.lock_record(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def is_python_launcher_role(relative: str) -> bool:
    """Whether a path is the environment's attested `bin/python*` role."""
    path = Path(relative)
    return (
        len(path.parts) == 2
        and path.parts[0] == "bin"
        and re.fullmatch(r"python(?:\d+(?:\.\d+)?)?", path.name) is not None
    )


def _attest_symlink(context: _DigestContext, path: Path, relative: str, hasher) -> None:
    target = os.readlink(path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"broken environment symlink: {relative}") from error
    if not resolved.is_relative_to(context.root):
        if not is_python_launcher_role(relative):
            raise ValueError(f"environment symlink escapes root: {relative}")
        _frame(
            hasher,
            b"L",
            relative,
            external_python_identity(path, context.python_provider),
        )
        return
    _frame(hasher, b"L", relative, target.encode("utf-8", "surrogateescape"))
