"""Standard-library-only observer identity, ownership, and read-only resolution."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform as host_platform
import stat
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

DOMAIN = "manifest-observer-runtime-v1"
RECORD_FIELDS = {
    "schema_version",
    "binding",
    "provider",
    "environment_sha256",
    "files",
    "proof",
}
PROVIDER_FIELDS = {"path", "implementation", "version", "build", "exe_sha256"}


class ObserverRuntimeError(ValueError):
    """Observer runtime validation or provisioning cannot proceed safely."""


def forbidden_root(path: Path, *roots: Path) -> Path | None:
    """Return the resolved root containing path, including symlink ancestors."""
    resolved = path.expanduser().resolve(strict=False)
    for root in roots:
        root = root.expanduser().resolve(strict=False)
        if resolved == root or resolved.is_relative_to(root):
            return root
    return None


def _check_observer_paths(bundle_root: Path, environ, *paths: Path) -> None:
    """Reject observer state only when it overlaps the installed bundle."""
    protected = (bundle_root,)
    for path in (*runtime_roots(environ), *paths):
        if violated := forbidden_root(path, *protected):
            raise ObserverRuntimeError(
                f"observer runtime must not resolve inside {violated}"
            )


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_regular(path: Path) -> bytes:
    for ancestor in path.parents:
        if ancestor.is_symlink():
            raise ValueError(f"observer file has a symlink ancestor: {path}")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"unsafe observer file: {path}")
        return stream.read()


def _bundle_relative_paths(root: Path, repository: Path | None) -> list[str]:
    if repository is None:
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if not _is_python_cache_path(path.relative_to(root).as_posix())
        )
    result = subprocess.run(
        (
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--full-name",
        ),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"unable to inventory tracked bundle files: {os.fsdecode(result.stderr).strip()}"
        )
    prefix = root.relative_to(repository).as_posix()
    if prefix == ".":
        prefix = ""
    entries: set[str] = set()
    for tracked in os.fsdecode(result.stdout).split("\0"):
        if not tracked:
            continue
        if prefix:
            if not tracked.startswith(prefix + "/"):
                continue
            relative = tracked[len(prefix) + 1 :]
        else:
            relative = tracked
        if not relative or _is_python_cache_path(relative):
            continue
        entries.add(relative)
        parts = relative.split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if not _is_python_cache_path(parent):
                entries.add(parent)
    return sorted(entries)


def _digest_bundle_paths(root: Path, relative_paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in relative_paths:
        path = root / relative
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError(f"unable to inspect bundle path {relative!r}") from error
        encoded = relative.encode("utf-8", errors="surrogateescape")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        if path.is_symlink():
            target = (
                path.readlink().as_posix().encode("utf-8", errors="surrogateescape")
            )
            digest.update(b"l" + len(target).to_bytes(8, "big") + target)
            continue
        if metadata.st_mode & 0o170000 == 0o040000:
            digest.update(b"d")
            continue
        digest.update(b"f")
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        except OSError as error:
            raise RuntimeError(f"unable to read bundle file {relative!r}") from error
    return digest.hexdigest()


def bundle_tree_sha256(root: Path, *, portable: bool = False) -> str:
    """Hash tracked checkout files or a portable bundle without Python caches."""
    root = root.expanduser().resolve()
    repository = None if portable else _git_checkout_root(root)
    return _digest_bundle_paths(root, _bundle_relative_paths(root, repository))


def _git_checkout_root(path: Path) -> Path | None:
    candidate = path
    while True:
        if (candidate / ".git").exists():
            return candidate
        if candidate.parent == candidate:
            return None
        candidate = candidate.parent


def _is_python_cache_path(relative: str) -> bool:
    return "__pycache__" in relative.split("/") or relative.endswith((".pyc", ".pyo"))


def platform_id() -> str:
    machine = host_platform.machine().casefold()
    machine = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64"}.get(
        machine, machine
    )
    return f"{host_platform.system().casefold()}-{machine}"


def runtime_roots(environ: dict[str, str] | os._Environ) -> tuple[Path, Path]:
    home = Path(environ.get("HOME") or Path.home())
    data = Path(environ.get("XDG_DATA_HOME") or home / ".local/share")
    state = Path(environ.get("XDG_STATE_HOME") or home / ".local/state")
    if not data.is_absolute() or not state.is_absolute():
        raise ValueError("observer XDG roots must be absolute")
    return data / "manifest/observer-runtimes", state / "manifest/observer-runtimes"


@dataclass(frozen=True)
class ObserverBinding:
    source_commit: str
    archive_sha256: str
    bundle_sha256: str
    lock_sha256: str
    platform: str

    @property
    def id(self) -> str:
        return digest(canonical(asdict(self)))


def generation_paths(
    binding: ObserverBinding, provider: dict, environ
) -> tuple[Path, Path]:
    """Paths are derived from validated identities, never accepted from records."""
    data, state = runtime_roots(environ)
    generation = digest(canonical(provider))
    relative = Path(binding.id) / generation
    return data / "environments" / relative, state / "records" / relative.with_suffix(
        ".json"
    )


def observer_key_path(environ) -> Path:
    """One authority for the shared XDG observer namespace, never receipt-local."""
    return runtime_roots(environ)[1] / "authority.key"


def authority(key_path: Path) -> bytes:
    secret = read_regular(key_path)
    if len(secret) != 32 or stat.S_IMODE(key_path.stat().st_mode) != 0o600:
        raise ValueError("unsafe observer ownership authority")
    return secret


def sign(document: dict, key_path: Path, *, domain: str = DOMAIN) -> dict:
    unsigned = {key: value for key, value in document.items() if key != "proof"}
    proof = hmac.new(
        authority(key_path),
        domain.encode() + b"\0" + canonical(unsigned),
        hashlib.sha256,
    ).hexdigest()
    return {**unsigned, "proof": proof}


def read_signed(path: Path, key_path: Path, *, domain: str = DOMAIN) -> dict:
    document = json.loads(read_regular(path))
    if not isinstance(document, dict) or not isinstance(document.get("proof"), str):
        raise ValueError("unsigned observer ownership marker")
    expected = sign(document, key_path, domain=domain)["proof"]
    if not hmac.compare_digest(document["proof"], expected):
        raise ValueError("observer ownership proof does not match")
    return document


def environment_inventory(root: Path, provider: dict) -> dict:
    """Inventory live bytes/modes and require every interpreter link to resolve."""
    return _environment_inventory(root, provider, resolve_links=True)


def retirement_inventory(root: Path, provider: dict) -> dict:
    """Read literal survivors for comparison with an authenticated original tree.

    Retirement may have removed an interpreter link or the lib64 alias's target
    already. This inventory alone is not live evidence or deletion authorization.
    """
    return _environment_inventory(root, provider, resolve_links=False)


def _environment_inventory(root: Path, provider: dict, *, resolve_links: bool) -> dict:
    """Preserve no-follow traversal and complete byte/mode coverage in both modes."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("observer environment is not a regular directory")
    if any(parent.is_symlink() for parent in root.parents):
        raise ValueError("observer environment has a symlink ancestor")
    files = {".": {"kind": "directory", "mode": stat.S_IMODE(root.stat().st_mode)}}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        entry = {"mode": stat.S_IMODE(mode)}
        if stat.S_ISLNK(mode):
            target = os.readlink(path)
            if relative == "lib64" and target == "lib":
                # UV's Linux layout has exactly this root-local directory alias.
                # A live proof requires the real directory; signed retirement
                # compares literal survivors even after that directory is gone.
                if resolve_links and not stat.S_ISDIR((root / "lib").lstat().st_mode):
                    raise ValueError("observer lib64 target is not a regular directory")
            elif path.parent == root / "bin" and path.name.startswith("python"):
                if resolve_links and str(path.resolve(strict=True)) != provider["path"]:
                    raise ValueError("observer symlink is not its pinned provider")
            else:
                raise ValueError(f"unexpected observer symlink: {relative}")
            entry.update(kind="symlink", target=target)
        elif stat.S_ISDIR(mode):
            entry.update(kind="directory")
        elif stat.S_ISREG(mode):
            data = read_regular(path)
            if path.suffix == ".pth" and any(
                line.strip() and not line.lstrip().startswith(b"#")
                for line in data.splitlines()
            ):
                raise ValueError(f"unexpected observer .pth: {relative}")
            entry.update(kind="file", sha256=digest(data))
        else:
            raise ValueError(f"special observer input: {relative}")
        files[relative] = entry
    return files


def validate_record(record: dict, binding: ObserverBinding, root: Path) -> None:
    if (
        set(record) != RECORD_FIELDS
        or type(record["schema_version"]) is not int
        or record["schema_version"] != 1
    ):
        raise ValueError("invalid observer record schema")
    if record["binding"] != asdict(binding):
        raise ValueError("observer record binding mismatch")
    provider = record["provider"]
    if (
        not isinstance(provider, dict)
        or set(provider) != PROVIDER_FIELDS
        or not all(isinstance(value, str) and value for value in provider.values())
    ):
        raise ValueError("invalid observer provider record")
    path = Path(provider["path"])
    if (
        not path.is_absolute()
        or path.is_symlink()
        or digest(read_regular(path)) != provider["exe_sha256"]
    ):
        raise ValueError("observer provider changed")
    files = record["files"]
    if not isinstance(files, dict) or any(
        not isinstance(name, str)
        or Path(name).is_absolute()
        or ".." in Path(name).parts
        for name in files
    ):
        raise ValueError("unsafe observer inventory path")
    actual = environment_inventory(root, provider)
    if files != actual or digest(canonical(actual)) != record["environment_sha256"]:
        raise ValueError("observer environment attestation changed")


def resolve_observer_runtime(bundle_root: Path, *, receipt_path: Path, environ) -> Path:
    """Resolve an installed interpreter only from an authoritative receipt."""
    receipt = json.loads(read_regular(receipt_path))
    checksum = bundle_tree_sha256(bundle_root, portable=True)
    if receipt.get("bundle_checksums", {}).get("manifest-workspace") != checksum:
        raise ValueError("installed observer bundle self-hash does not match receipt")
    project = bundle_root / "runtime/observer"
    binding = ObserverBinding(
        receipt["source_commit"],
        receipt["archive_sha256"],
        checksum,
        digest(read_regular(project / "uv.lock")),
        platform_id(),
    )
    data, state = runtime_roots(environ)
    records = state / "records" / binding.id
    store = (
        data
        / "toolchains"
        / digest(read_regular(project / "uv-toolchain.lock.json"))
        / binding.platform
    )
    _check_observer_paths(bundle_root, environ, records, store)
    if not records.is_dir() or records.is_symlink():
        raise ValueError("observer runtime is missing; run authorized install/update")
    errors = []
    for record_path in sorted(records.glob("*.json")):
        try:
            record = read_signed(record_path, observer_key_path(environ))
            provider = record["provider"]
            root, expected_record = generation_paths(binding, provider, environ)
            _check_observer_paths(
                bundle_root, environ, root, root.parent, expected_record.parent
            )
            if record_path != expected_record:
                raise ValueError("observer record generation mismatch")
            validate_record(record, binding, root)
            return root / "bin/python"
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(str(error))
    raise ValueError(
        "observer runtime unavailable; run authorized install/update: "
        + "; ".join(errors)
    )
