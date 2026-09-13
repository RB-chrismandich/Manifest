"""No-follow store mutations, manifest recording, and environment dispatch."""

from __future__ import annotations

import fcntl
import io
import json
import os
import stat
import subprocess
import tarfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import toolchain
from . import toolchain_materialize as materialize


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _open_directory_at(parent_fd: int, name: str, *, create: bool) -> int:
    """Open one store-owned directory without ever resolving a link."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise ValueError("unsafe toolchain store ancestor") from error


def _store_fd(store: Path) -> int:
    """Open the canonical store root and reject an attacker-supplied link."""
    try:
        store.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"unsafe toolchain store: {error}") from error
    try:
        return os.open(store, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError("unsafe toolchain store") from error


@dataclass(frozen=True, slots=True)
class StorePath:
    """A verified store-relative destination, addressed through live FDs."""

    parent_fd: int
    name: str

    def close(self) -> None:
        os.close(self.parent_fd)


def store_destination(
    store: Path, relative: str, *, create_parents: bool = True
) -> StorePath:
    """Resolve a relative store sink through no-follow directory descriptors."""
    if not _safe_relative(relative):
        raise ValueError("toolchain destination escapes store")
    parts = Path(relative).parts
    root_fd = _store_fd(store)
    current_fd = root_fd
    try:
        for component in parts[:-1]:
            next_fd = _open_directory_at(current_fd, component, create=create_parents)
            os.close(current_fd)
            current_fd = next_fd
    except (OSError, ValueError):
        os.close(current_fd)
        raise
    return StorePath(current_fd, parts[-1])


def _existing_kind(destination: StorePath) -> int | None:
    try:
        return os.stat(
            destination.name, dir_fd=destination.parent_fd, follow_symlinks=False
        ).st_mode
    except FileNotFoundError:
        return None


def _reject_existing(destination: StorePath, expected: int | None = None) -> None:
    mode = _existing_kind(destination)
    if mode is None:
        return
    if stat.S_ISLNK(mode) or (expected is not None and not expected(mode)):
        raise ValueError("unsafe toolchain store destination")


def archive_member_bytes(data: bytes, path_in_archive: str) -> bytes:
    """Return one regular archive member without extracting its path."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            member = archive.extractfile(path_in_archive)
            if member is None:
                raise ValueError(f"{path_in_archive!r} not found in archive")
            return member.read()
    except tarfile.ReadError:
        return data


def write_file(store: Path, relative: str, content: bytes, mode: int) -> None:
    """Verify then atomically replace one regular store file via `renameat`."""
    destination = store_destination(store, relative)
    temporary = f".{destination.name}.{os.getpid()}.tmp"
    try:
        _reject_existing(destination, stat.S_ISREG)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=destination.parent_fd)
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=destination.parent_fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary,
            destination.name,
            src_dir_fd=destination.parent_fd,
            dst_dir_fd=destination.parent_fd,
        )
        os.chmod(
            destination.name, mode, dir_fd=destination.parent_fd, follow_symlinks=False
        )
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=destination.parent_fd)
        destination.close()


def _remove_tree_at(parent_fd: int, name: str) -> None:
    """Delete an old store tree only through already-open no-follow FDs."""
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        for entry in os.listdir(fd):
            mode = os.stat(entry, dir_fd=fd, follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                _remove_tree_at(fd, entry)
            else:
                os.unlink(entry, dir_fd=fd)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=parent_fd)


@dataclass(slots=True)
class StagedDirectory:
    """A private stage which publishes only after its owner explicitly commits."""

    path: Path
    committed: bool = False

    def commit(self) -> None:
        self.committed = True

    def __truediv__(self, other: str) -> Path:
        return self.path / other


@contextmanager
def staged_directory(store: Path, relative: str) -> Iterator[StagedDirectory]:
    """Build in a restrictive sibling stage, publishing only on `commit()`."""
    destination = store_destination(store, relative)
    stage = f".{destination.name}.{os.getpid()}.staging"
    backup = f".{destination.name}.{os.getpid()}.previous"
    stage_path = store.resolve(strict=True).joinpath(*Path(relative).parts[:-1], stage)
    transaction = StagedDirectory(stage_path)
    try:
        _reject_existing(destination, stat.S_ISDIR)
        with suppress(FileNotFoundError):
            _remove_tree_at(destination.parent_fd, stage)
        os.mkdir(stage, 0o700, dir_fd=destination.parent_fd)
        yield transaction
        if not transaction.committed:
            return
        _reject_existing(destination, stat.S_ISDIR)
        if _existing_kind(destination) is not None:
            with suppress(FileNotFoundError):
                _remove_tree_at(destination.parent_fd, backup)
            os.replace(
                destination.name,
                backup,
                src_dir_fd=destination.parent_fd,
                dst_dir_fd=destination.parent_fd,
            )
        os.replace(
            stage,
            destination.name,
            src_dir_fd=destination.parent_fd,
            dst_dir_fd=destination.parent_fd,
        )
        with suppress(FileNotFoundError):
            _remove_tree_at(destination.parent_fd, backup)
    finally:
        with suppress(FileNotFoundError):
            _remove_tree_at(destination.parent_fd, stage)
        destination.close()


def _with_store_lock(store: Path, body: Callable[[], dict]) -> dict:
    """Serialize mutations after opening a no-follow store root."""
    root_fd = _store_fd(store)
    try:
        fd = os.open(
            ".provision.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        with os.fdopen(fd, "a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            return body()
    finally:
        os.close(root_fd)


def _write_manifest(store: Path, manifest: Mapping) -> None:
    write_file(
        store,
        "manifest.json",
        json.dumps(manifest, sort_keys=True).encode("utf-8"),
        0o600,
    )


def _load_manifest(store: Path, lock: Mapping, platform: str) -> dict:
    manifest = toolchain.load_store_manifest(store)
    if (
        manifest is None
        or manifest.get("lock_digest") != toolchain.lock_digest(lock)
        or manifest.get("platform") != platform
    ):
        return {
            "schema_version": 1,
            "lock_digest": toolchain.lock_digest(lock),
            "platform": platform,
            "tools": {},
        }
    return manifest


def _resolved_commit(repo_root: Path) -> str | None:
    result = subprocess.run(
        ("git", "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _attestation_metadata(ctx: Any, bundle: str) -> dict[str, str | None]:
    entry = ctx.lock["tools"][bundle]
    platform_entry = entry["platforms"][ctx.platform]
    return {
        "platform": ctx.platform,
        "version": entry["version"],
        "source": platform_entry["url"],
        "resolved_commit": _resolved_commit(ctx.repo_root),
    }


@dataclass(frozen=True, slots=True)
class BinaryArtifacts:
    source_sha256: str | None
    primary_relative: str
    primary_sha256: str
    extra: Mapping[str, tuple[str, str]] = field(default_factory=dict)


def _record_bundle(ctx: Any, bundle: str, artifacts: BinaryArtifacts) -> None:
    def body() -> dict:
        manifest = _load_manifest(ctx.store, ctx.lock, ctx.platform)
        executables: dict[str, dict[str, str]] = {
            f"bin/{bundle}": {
                "path": artifacts.primary_relative,
                "sha256": artifacts.primary_sha256,
            }
        }
        for name, (relative, digest) in artifacts.extra.items():
            executables[f"bin/{name}"] = {
                "path": relative,
                "sha256": digest,
                "interpreter": artifacts.primary_relative,
                "interpreter_sha256": artifacts.primary_sha256,
            }
        manifest["tools"][bundle] = {
            **_attestation_metadata(ctx, bundle),
            "source_sha256": artifacts.source_sha256,
            "executables": executables,
        }
        _write_manifest(ctx.store, manifest)
        return manifest

    _with_store_lock(ctx.store, body)


def _record_env_bundle(
    ctx: Any, bundle: str, source_sha256: str, scripts: Mapping[str, str]
) -> None:
    def body() -> dict:
        manifest = _load_manifest(ctx.store, ctx.lock, ctx.platform)
        manifest["tools"][bundle] = {
            **_attestation_metadata(ctx, bundle),
            "source_sha256": source_sha256,
            "executables": {
                f"bin/{name}": {"path": relative} for name, relative in scripts.items()
            },
        }
        _write_manifest(ctx.store, manifest)
        return manifest

    _with_store_lock(ctx.store, body)


class _SourceUnavailable(RuntimeError):
    pass


def _read_source_bytes(ctx: Any, url: str) -> bytes:
    if not url.startswith("file://"):
        raise _SourceUnavailable(f"source unavailable: unsupported local URL: {url}")
    relative = url.removeprefix("file://")
    if not _safe_relative(relative):
        raise _SourceUnavailable(f"source unavailable: unsafe path: {relative}")
    root = ctx.repo_root.resolve(strict=False)
    try:
        path = (ctx.repo_root / relative).resolve(strict=True)
    except OSError as error:
        raise _SourceUnavailable(f"source unavailable: {relative}: {error}") from error
    if not path.is_relative_to(root) or not path.is_file():
        raise _SourceUnavailable(f"source unavailable: unsafe path: {relative}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise _SourceUnavailable(f"source unavailable: {relative}: {error}") from error


def _materialize_env(
    ctx: Any, bundle: str, entry: Mapping, env_root: Path, names: list[str]
) -> dict[str, str]:
    ctx_m = materialize.MaterializeContext(
        ctx.lock, ctx.store, ctx.platform, ctx.repo_root, ctx.env
    )
    if bundle == "project-env":
        materialize.materialize_project_env(ctx_m, env_root)
        return materialize.python_env_console_scripts(env_root, names)
    if bundle == "config-env":
        materialize.materialize_python_env(
            ctx_m, env_root, project_relative="configs/claude"
        )
        return materialize.python_env_console_scripts(env_root, names)
    if entry["kind"] == "python-env":
        materialize.materialize_python_env(ctx_m, env_root)
        return materialize.python_env_console_scripts(env_root, names)
    materialize.materialize_node_env(ctx_m, env_root, ctx.fetcher)
    return materialize.node_env_console_scripts(env_root, names)
