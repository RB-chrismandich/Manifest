# constitution: exempt C-SIZE -- descriptor-held backup operations share one filesystem trust boundary.
"""Private content-addressed backups for destructive Codex plugin repair."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from manifest_agent.codex_config import CodexConfigError, set_manifest_plugin_enabled


class CodexPluginBackupError(RuntimeError):
    """A plugin backup could not be captured or restored safely."""


MAX_OWNED_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class OwnedFileBackup:
    """One bounded regular file retained in the shared private archive layer."""

    archive_path: str
    archive_sha256: str
    archive_size: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OwnedFileBackup:
        fields = {"archive_path", "archive_sha256", "archive_size"}
        if (
            set(value) != fields
            or not isinstance(value.get("archive_path"), str)
            or not isinstance(value.get("archive_sha256"), str)
            or len(value["archive_sha256"]) != 64
            or not isinstance(value.get("archive_size"), int)
            or value["archive_size"] < 0
            or value["archive_size"] > MAX_OWNED_FILE_BYTES
        ):
            raise CodexPluginBackupError("owned file backup has an invalid schema")
        return cls(**{field: value[field] for field in fields})


@dataclass(frozen=True)
class CodexPluginBackup:
    plugin_id: str
    version: str
    enabled: bool
    installed_path: str
    archive_path: str
    archive_sha256: str
    archive_size: int
    installed_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CodexPluginBackup:
        fields = (
            "plugin_id",
            "version",
            "enabled",
            "installed_path",
            "archive_path",
            "archive_sha256",
            "archive_size",
            "installed_sha256",
        )
        if set(value) != set(fields):
            raise CodexPluginBackupError("plugin backup journal has an invalid schema")
        if not all(
            isinstance(value[field], str)
            for field in fields
            if field not in {"enabled", "archive_size"}
        ):
            raise CodexPluginBackupError(
                "plugin backup journal has invalid string fields"
            )
        if not isinstance(value["enabled"], bool):
            raise CodexPluginBackupError(
                "plugin backup journal has an invalid enabled field"
            )
        if not isinstance(value["archive_size"], int) or value["archive_size"] < 0:
            raise CodexPluginBackupError(
                "plugin backup journal has an invalid archive size"
            )
        return cls(**{field: value[field] for field in fields})


def capture_owned_file_backup(
    path: Path, env: Mapping[str, str] | None = None
) -> tuple[OwnedFileBackup, int, str]:
    """Capture one regular file through a single bounded no-follow descriptor."""
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_descriptor = os.open(path, source_flags)
    except OSError as error:
        raise CodexPluginBackupError("owned file is unavailable for backup") from error
    try:
        metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CodexPluginBackupError("owned file backup source is not regular")
        if metadata.st_size > MAX_OWNED_FILE_BYTES:
            raise CodexPluginBackupError("owned file exceeds the backup size limit")
        content = _read_descriptor_bounded(source_descriptor, MAX_OWNED_FILE_BYTES)
        digest = hashlib.sha256(content).hexdigest()
        root = _owned_file_backup_root(env)
        destination = root / f"{digest}.bin"
        root_descriptor = _ensure_directory_chain(root)
        descriptor, temporary_name = _create_temporary_at(root_descriptor)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(
                    temporary_name,
                    destination.name,
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                os.chmod(destination.name, 0o600, dir_fd=root_descriptor)
                os.fsync(root_descriptor)
            # constitution: exempt C-ERR -- an existing content-addressed archive is verified below.
            except FileExistsError:
                pass
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=root_descriptor)
            os.close(root_descriptor)
        backup = OwnedFileBackup(str(destination), digest, len(content))
        verified = _open_verified_content(
            backup.archive_path,
            backup.archive_sha256,
            backup.archive_size,
            configured_root=root,
        )
        os.close(verified)
        return backup, stat.S_IMODE(metadata.st_mode), digest
    finally:
        os.close(source_descriptor)


def read_owned_file_backup(
    backup: OwnedFileBackup,
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
) -> bytes:
    """Read verified backup bytes from the same descriptor used for verification."""
    descriptor = _open_verified_content(
        backup.archive_path,
        backup.archive_sha256,
        backup.archive_size,
        configured_root=root or _owned_file_backup_root(env),
    )
    try:
        return _read_descriptor_bounded(descriptor, MAX_OWNED_FILE_BYTES)
    finally:
        os.close(descriptor)


def verify_owned_file_backup(
    backup: OwnedFileBackup,
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
) -> None:
    descriptor = _open_verified_content(
        backup.archive_path,
        backup.archive_sha256,
        backup.archive_size,
        configured_root=root or _owned_file_backup_root(env),
    )
    os.close(descriptor)


# constitution: exempt C-SIZE -- quarantine and unlink must share the held root descriptor.
def remove_owned_file_backup(
    backup: OwnedFileBackup,
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
) -> None:
    path = Path(backup.archive_path)
    configured_root = root or _owned_file_backup_root(env)
    if path != configured_root.expanduser() / f"{backup.archive_sha256}.bin":
        raise CodexPluginBackupError("backup escaped the owned archive root")
    try:
        root_descriptor = _open_directory_chain(configured_root)
    except FileNotFoundError:
        return
    except OSError as error:
        raise CodexPluginBackupError("plugin backup root is unavailable") from error
    quarantine = f".{path.name}.retire-{secrets.token_hex(16)}"
    quarantined = False
    try:
        descriptor = _open_verified_entry_at(root_descriptor, path.name, backup)
        if descriptor is None:
            return
        try:
            identity = os.fstat(descriptor)
            _owned_archive_remove_boundary(path)
            os.rename(
                path.name,
                quarantine,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
            )
            quarantined = True
            moved = os.stat(quarantine, dir_fd=root_descriptor, follow_symlinks=False)
            if (moved.st_dev, moved.st_ino) != (identity.st_dev, identity.st_ino):
                os.rename(
                    quarantine,
                    path.name,
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                )
                quarantined = False
                raise CodexPluginBackupError(
                    "owned backup changed at the final removal boundary"
                )
            _owned_archive_remove_quarantined_boundary(path)
            os.unlink(quarantine, dir_fd=root_descriptor)
            quarantined = False
            os.fsync(root_descriptor)
        finally:
            os.close(descriptor)
    finally:
        if quarantined:
            try:
                os.stat(path.name, dir_fd=root_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                with suppress(FileNotFoundError):
                    os.rename(
                        quarantine,
                        path.name,
                        src_dir_fd=root_descriptor,
                        dst_dir_fd=root_descriptor,
                    )
        os.close(root_descriptor)


def _open_verified_entry_at(
    root_descriptor: int, name: str, backup: OwnedFileBackup
) -> int | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != backup.archive_size
            or _sha256_descriptor(descriptor) != backup.archive_sha256
        ):
            raise CodexPluginBackupError("backup is missing or failed verification")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def owned_file_backup_root(env: Mapping[str, str] | None = None) -> Path:
    """Return the configured private root used for authenticated file archives."""
    return _owned_file_backup_root(env)


# constitution: exempt C-SIZE -- capture, fsync, publish, and verification form one atomic operation.
def capture_plugin_backup(
    row: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
    *,
    require_manifest_suffix: bool = True,
) -> CodexPluginBackup:
    """Archive the exact installed directory before native removal."""
    plugin_id = row.get("pluginId")
    version = row.get("version")
    enabled = row.get("enabled")
    installed = row.get("installedPath")
    if not isinstance(installed, str):
        source = row.get("source")
        installed = source.get("path") if isinstance(source, Mapping) else None
    if (
        not isinstance(plugin_id, str)
        or not plugin_id
        or (require_manifest_suffix and not plugin_id.endswith("@manifest"))
        or not isinstance(version, str)
        or not version
        or not isinstance(enabled, bool)
        or not isinstance(installed, str)
        or not installed
    ):
        raise CodexPluginBackupError(
            "installed Manifest plugin lacks backup-safe native metadata"
        )
    installed_path = Path(installed).expanduser()
    if installed_path.is_symlink() or not installed_path.is_dir():
        raise CodexPluginBackupError(
            "installed Manifest plugin path is not a regular directory"
        )
    installed_path = installed_path.resolve(strict=True)
    root = _backup_root(env)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".capture-", suffix=".tar", dir=root)
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        with tarfile.open(temporary, mode="w", dereference=False) as archive:
            archive.add(installed_path, arcname="plugin", recursive=True)
        _fsync_file(temporary)
        digest = _sha256_file(temporary)
        destination = root / f"{digest}.tar"
        if destination.exists():
            if destination.is_symlink() or _sha256_file(destination) != digest:
                raise CodexPluginBackupError(
                    "content-addressed plugin backup failed verification"
                )
            temporary.unlink()
            temporary = None
        else:
            os.replace(temporary, destination)
            temporary = None
            os.chmod(destination, 0o600)
            _fsync_directory(root)
        if _sha256_file(destination) != digest:
            raise CodexPluginBackupError("plugin backup digest verification failed")
        return CodexPluginBackup(
            plugin_id,
            version,
            enabled,
            str(installed_path),
            str(destination),
            digest,
            destination.stat().st_size,
            plugin_tree_sha256(installed_path),
        )
    except (OSError, tarfile.TarError) as error:
        raise CodexPluginBackupError(
            "unable to capture installed plugin backup"
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_plugin_backup(backup: CodexPluginBackup) -> None:
    """Restore captured files and any inferred native Codex registration."""
    installed_path = Path(backup.installed_path)
    registration = _codex_registration(backup, installed_path)
    descriptor = _open_verified_archive(backup)
    try:
        if installed_path.exists() or installed_path.is_symlink():
            raise CodexPluginBackupError(
                "plugin restore blocked because the installed path changed"
            )
        installed_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(
            prefix=".manifest-restore-", dir=installed_path.parent
        ) as temporary_name:
            temporary = Path(temporary_name)
            try:
                stream = os.fdopen(descriptor, "rb")
                descriptor = -1
                with stream, tarfile.open(fileobj=stream, mode="r:") as archive:
                    _validate_members(archive)
                    archive.extractall(temporary, filter="fully_trusted")
            except (OSError, tarfile.TarError) as error:
                raise CodexPluginBackupError(
                    "unable to extract plugin backup"
                ) from error
            restored = temporary / "plugin"
            if restored.is_symlink() or not restored.is_dir():
                raise CodexPluginBackupError("plugin backup has an invalid root")
            os.replace(restored, installed_path)
            _fsync_directory(installed_path.parent)
            if plugin_tree_sha256(installed_path) != backup.installed_sha256:
                _discard_restored_tree(installed_path, backup)
                raise CodexPluginBackupError(
                    "restored plugin content failed verification"
                )
            if registration is not None:
                try:
                    set_manifest_plugin_enabled(
                        registration, backup.plugin_id, backup.enabled
                    )
                except CodexConfigError as error:
                    _discard_restored_tree(installed_path, backup)
                    raise CodexPluginBackupError(
                        "unable to restore Codex native plugin registration"
                    ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _codex_registration(backup: CodexPluginBackup, installed_path: Path) -> Path | None:
    parents = installed_path.parents
    if len(parents) < 5 or parents[2].name != "cache" or parents[3].name != "plugins":
        return None
    marketplace = parents[1].name
    plugin = parents[0].name
    if marketplace != "manifest":
        return None
    if (
        backup.plugin_id != f"{plugin}@manifest"
        or backup.version != installed_path.name
    ):
        raise CodexPluginBackupError(
            "Codex plugin backup does not match its native cache identity"
        )
    return parents[4] / "config.toml"


def _discard_restored_tree(path: Path, backup: CodexPluginBackup) -> None:
    quarantine = path.with_name(
        f".{path.name}.registration-failed-{secrets.token_hex(8)}"
    )
    try:
        os.replace(path, quarantine)
        if plugin_tree_sha256(quarantine) != backup.installed_sha256:
            os.replace(quarantine, path)
            raise CodexPluginBackupError(
                "restored plugin changed before registration rollback"
            )
        shutil.rmtree(quarantine)
        _fsync_directory(path.parent)
    except CodexPluginBackupError:
        raise
    except OSError as error:
        if quarantine.exists() and not path.exists():
            with suppress(OSError):
                os.replace(quarantine, path)
        raise CodexPluginBackupError(
            "unable to remove unregistered restored plugin files"
        ) from error


def verify_plugin_backup(backup: CodexPluginBackup) -> None:
    """Require the retained archive to match its content-addressed authority."""
    descriptor = _open_verified_archive(backup)
    try:
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        with stream, tarfile.open(fileobj=stream, mode="r:") as archive:
            _validate_members(archive)
    except (OSError, tarfile.TarError) as error:
        raise CodexPluginBackupError("plugin backup failed verification") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def remove_plugin_backup(backup: CodexPluginBackup) -> None:
    path = Path(backup.archive_path)
    try:
        descriptor = _open_verified_archive(backup)
    except CodexPluginBackupError:
        if not path.exists():
            return
        raise
    os.close(descriptor)
    root_descriptor = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.unlink(path.name, dir_fd=root_descriptor)
    finally:
        os.close(root_descriptor)
    if path.parent.exists():
        _fsync_directory(path.parent)


def plugin_tree_sha256(path: Path) -> str:
    """Hash one installed tree without following links outside its root."""
    if path.is_symlink() or not path.is_dir():
        raise CodexPluginBackupError("installed plugin path is not a regular directory")
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        relative = child.relative_to(path).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if child.is_symlink():
            target = os.readlink(child).encode()
            digest.update(b"l" + len(target).to_bytes(8, "big") + target)
        elif child.is_dir():
            digest.update(b"d")
        elif child.is_file():
            digest.update(b"f")
            with child.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            raise CodexPluginBackupError("installed plugin tree has an unsafe entry")
    return digest.hexdigest()


def _backup_root(env: Mapping[str, str] | None) -> Path:
    return _state_root(env) / "manifest" / "codex-plugin-backups"


def _owned_file_backup_root(env: Mapping[str, str] | None) -> Path:
    return _state_root(env) / "manifest" / "owned-file-backups"


def _state_root(env: Mapping[str, str] | None) -> Path:
    values = os.environ if env is None else env
    if values.get("XDG_STATE_HOME"):
        return Path(values["XDG_STATE_HOME"]).expanduser()
    home = Path(values.get("HOME", str(Path.home()))).expanduser()
    return home / ".local" / "state"


def _open_verified_archive(backup: CodexPluginBackup) -> int:
    return _open_verified_content(
        backup.archive_path,
        backup.archive_sha256,
        backup.archive_size,
        root_name="codex-plugin-backups",
    )


def _open_verified_content(
    raw_path: str,
    digest: str,
    size: int,
    *,
    root_name: str | None = None,
    configured_root: Path | None = None,
) -> int:
    archive_path = Path(raw_path)
    if configured_root is not None:
        root = configured_root.expanduser()
        if not root.is_absolute() or archive_path != root / f"{digest}.bin":
            raise CodexPluginBackupError("backup escaped the owned archive root")
    elif root_name is not None and (
        not archive_path.is_absolute() or archive_path.parent.name != root_name
    ):
        raise CodexPluginBackupError("backup escaped the owned archive root")
    try:
        root_descriptor = _open_directory_chain(archive_path.parent)
    except OSError as error:
        raise CodexPluginBackupError("plugin backup root is unavailable") from error
    try:
        _owned_archive_boundary(archive_path)
        descriptor = os.open(
            archive_path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
    except OSError as error:
        raise CodexPluginBackupError("plugin backup is missing") from error
    finally:
        os.close(root_descriptor)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != size
            or _sha256_descriptor(descriptor) != digest
        ):
            raise CodexPluginBackupError("backup is missing or failed verification")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_directory_chain(path: Path) -> int:
    """Open an absolute directory without following any intermediate symlink."""
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise CodexPluginBackupError("backup root must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(expanded.anchor, flags)
    try:
        for part in expanded.parts[1:]:
            _owned_archive_traversal_boundary(expanded, part)
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _ensure_directory_chain(path: Path) -> int:
    """Create and open an absolute directory chain without following symlinks."""
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise CodexPluginBackupError("backup root must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(expanded.anchor, flags)
    try:
        for part in expanded.parts[1:]:
            _owned_archive_traversal_boundary(expanded, part)
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                # constitution: exempt C-ERR -- a concurrent creator is verified by the no-follow open.
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        os.fchmod(descriptor, 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _create_temporary_at(root_descriptor: int) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(128):
        name = f".capture-{secrets.token_hex(16)}.bin"
        try:
            return os.open(name, flags, 0o600, dir_fd=root_descriptor), name
        except FileExistsError:
            continue
    raise CodexPluginBackupError("unable to allocate owned backup temporary file")


def _owned_archive_traversal_boundary(root: Path, component: str) -> None:
    """Test seam immediately before one no-follow directory traversal."""
    del root, component


def _owned_archive_boundary(path: Path) -> None:
    """Test seam immediately before descriptor-relative archive entry open."""
    del path


def _owned_archive_remove_boundary(path: Path) -> None:
    """Test seam immediately before descriptor-relative archive quarantine."""
    del path


def _owned_archive_remove_quarantined_boundary(path: Path) -> None:
    """Test seam after quarantine and before unlink/fsync on the held root."""
    del path


def _validate_members(archive: tarfile.TarFile) -> None:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or not path.parts
            or path.parts[0] != "plugin"
            or ".." in path.parts
        ):
            raise CodexPluginBackupError("plugin backup contains an unsafe path")
        if member.issym() or member.islnk():
            target = PurePosixPath(member.linkname)
            if target.is_absolute() or ".." in target.parts:
                raise CodexPluginBackupError("plugin backup contains an unsafe link")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise CodexPluginBackupError("unable to read plugin backup") from error
    return digest.hexdigest()


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _read_descriptor_bounded(descriptor: int, limit: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(64 * 1024, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise CodexPluginBackupError("owned file exceeds the backup size limit")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
