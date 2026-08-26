"""Build a deterministic, immutable Manifest domain-bundle release."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import yaml

from manifest_agent.adapters.registry import AdapterRegistry
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    ContractError,
    load_domain_contracts,
)
from manifest_agent.models import BundleContract

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40,64}$")
_ARCHIVE_PREFIX = "manifest-plugins"
_METADATA_NAME = "manifest-release.json"


class ReleaseBuildError(RuntimeError):
    """The source tree cannot produce an immutable release artifact."""


@dataclass(frozen=True)
class FileRecord:
    """One normalized release file and its content identity."""

    path: str
    data: bytes
    mode: int
    sha256: str


@dataclass(frozen=True)
class TrackedBundleFile:
    """A safe regular file selected from the immutable HEAD tree."""

    path: str
    object_id: str
    mode: int


@dataclass(frozen=True)
class ReleaseBuild:
    """Paths and immutable identities produced by one release build."""

    archive: Path
    metadata: Path
    version: str
    commit: str
    archive_sha256: str


def build_release(
    repo_root: Path,
    output_dir: Path,
    archive_base_url: str,
) -> ReleaseBuild:
    """Validate ``repo_root`` and write immutable release files to ``output_dir``."""
    root = _git_root(repo_root)
    _require_clean_tree(root)
    commit = _git(root, "rev-parse", "HEAD").lower()
    if not _COMMIT.fullmatch(commit):
        raise ReleaseBuildError("repository HEAD must be a full immutable SHA-1")
    contracts = _load_contracts(root)
    _verify_generated_views(root)
    version = _release_version(contracts)
    _validate_generated_views(root, contracts)
    base_url = _validate_archive_base_url(archive_base_url)

    archive_name = f"{_ARCHIVE_PREFIX}-{version}.tar.gz"
    output = output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir():
        raise ReleaseBuildError(f"release output is not a directory: {output}")

    marketplace = _release_marketplace(contracts)
    records = _release_files(root, marketplace)
    archive = output / archive_name
    _write_archive(archive, version, records)
    archive_sha256 = _sha256_path(archive)
    metadata = output / _METADATA_NAME
    document = _release_document(
        archive_name=archive_name,
        archive_base_url=base_url,
        archive_sha256=archive_sha256,
        commit=commit,
        contracts=contracts,
        records=records,
        version=version,
    )
    _write_bytes(metadata, _json_bytes(document))
    return ReleaseBuild(archive, metadata, version, commit, archive_sha256)


def _git_root(candidate: Path) -> Path:
    root = candidate.expanduser().resolve()
    completed = _run(("git", "-C", str(root), "rev-parse", "--show-toplevel"))
    if completed.returncode != 0:
        raise ReleaseBuildError(f"release source is not a git checkout: {root}")
    git_root = Path(completed.stdout.strip()).resolve()
    if git_root != root:
        raise ReleaseBuildError(
            f"release source must be the checkout root, not a subdirectory: {root}"
        )
    return git_root


def _require_clean_tree(root: Path) -> None:
    status = _run(
        ("git", "-C", str(root), "status", "--porcelain", "--untracked-files=all")
    )
    if status.returncode != 0:
        raise ReleaseBuildError("unable to inspect release source status")
    if status.stdout:
        raise ReleaseBuildError("release source tree must be clean")


def _git(root: Path, *arguments: str) -> str:
    completed = _run(("git", "-C", str(root), *arguments))
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReleaseBuildError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _run(
    arguments: tuple[str, ...], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as error:
        raise ReleaseBuildError(f"unable to run {arguments[0]!r}: {error}") from error


def _verify_generated_views(root: Path) -> None:
    generator = root / "tools" / "generate_plugin_views.py"
    if not generator.is_file():
        raise ReleaseBuildError("release source is missing generated-view verifier")
    environment = os.environ.copy()
    source_path = str(root / "src")
    if inherited := environment.get("PYTHONPATH"):
        source_path = os.pathsep.join((source_path, inherited))
    environment["PYTHONPATH"] = source_path
    completed = _run(
        (sys.executable, str(generator), "--check", "--repo-root", str(root)),
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReleaseBuildError(f"generated views are not clean: {detail}")


def _load_contracts(root: Path) -> tuple[BundleContract, ...]:
    try:
        contracts = load_domain_contracts(root / "plugins")
    except ContractError as error:
        raise ReleaseBuildError(f"invalid domain contracts: {error}") from error
    if tuple(contract.name for contract in contracts) != DOMAIN_BUNDLES:
        raise ReleaseBuildError(
            "domain contracts do not match the canonical bundle set"
        )
    return contracts


def _release_version(contracts: tuple[BundleContract, ...]) -> str:
    versions = {contract.version for contract in contracts}
    if len(versions) != 1:
        formatted = ", ".join(sorted(str(version) for version in versions))
        raise ReleaseBuildError(f"domain bundle versions must match: {formatted}")
    version = versions.pop()
    if not isinstance(version, str) or not version:
        raise ReleaseBuildError("domain bundle version is invalid")
    return version


def _validate_generated_views(
    root: Path, contracts: tuple[BundleContract, ...]
) -> None:
    for contract in contracts:
        name = contract.name
        version = contract.version
        bundle = root / "plugins" / name
        for relative in (
            ".claude-plugin/plugin.json",
            "gemini-extension.json",
            "plugin.json",
            ".devin-plugin/plugin.json",
        ):
            path = bundle / relative
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ReleaseBuildError(
                    f"{name}: invalid generated view {relative}: {error}"
                ) from error
            if not isinstance(document, dict):
                raise ReleaseBuildError(
                    f"{name}: generated view {relative} is not an object"
                )
            if document.get("name") != name or document.get("version") != version:
                raise ReleaseBuildError(
                    f"{name}: generated view {relative} does not match its contract"
                )


def _validate_archive_base_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ReleaseBuildError("archive base URL must be credential-free HTTPS")
    return value.rstrip("/")


def _release_marketplace(contracts: tuple[BundleContract, ...]) -> bytes:
    plugins = [
        {
            "category": contract.category,
            "description": contract.description,
            "name": contract.name,
            "source": f"./plugins/{contract.name}",
            "version": contract.version,
        }
        for contract in contracts
    ]
    document = {
        "description": "Manifest agent capabilities partitioned into eight portable domain bundles.",
        "name": "manifest",
        "owner": {"name": "ReefBytes"},
        "plugins": plugins,
    }
    return _json_bytes(document)


def _release_files(root: Path, marketplace: bytes) -> tuple[FileRecord, ...]:
    records = [
        FileRecord(
            ".claude-plugin/marketplace.json",
            marketplace,
            0o644,
            hashlib.sha256(marketplace).hexdigest(),
        )
    ]
    tracked_files: list[TrackedBundleFile] = []
    for bundle_name in DOMAIN_BUNDLES:
        bundle = root / "plugins" / bundle_name
        if not bundle.is_dir():
            raise ReleaseBuildError(f"missing domain bundle directory: {bundle_name}")
        tracked_files.extend(_tracked_bundle_files(root, bundle_name))
    blobs = _git_blob_bytes(root, tuple(tracked_files))
    for tracked in tracked_files:
        data = blobs[tracked.object_id]
        records.append(
            FileRecord(
                tracked.path,
                data,
                tracked.mode,
                hashlib.sha256(data).hexdigest(),
            )
        )
    ordered = tuple(sorted(records, key=lambda record: record.path))
    if len({record.path for record in ordered}) != len(ordered):
        raise ReleaseBuildError("release file inventory contains duplicate paths")
    return ordered


def _tracked_bundle_files(
    root: Path, bundle_name: str
) -> tuple[TrackedBundleFile, ...]:
    """Return only regular bundle blobs committed by the immutable HEAD."""
    try:
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(root),
                "ls-tree",
                "-r",
                "-z",
                "HEAD",
                "--",
                f"plugins/{bundle_name}",
            ),
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise ReleaseBuildError(
            "unable to inventory tracked release bundle files"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ReleaseBuildError(
            f"unable to inventory tracked release bundle files: {detail}"
        )

    prefix = ("plugins", bundle_name)
    files: list[TrackedBundleFile] = []
    for entry in completed.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, separator, encoded_path = entry.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise ReleaseBuildError("unable to parse tracked release bundle files")
        mode, object_type, encoded_object_id = fields
        try:
            relative = encoded_path.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ReleaseBuildError(
                "tracked release path is not valid UTF-8"
            ) from error
        path_parts = PurePosixPath(relative)
        if (
            path_parts.is_absolute()
            or ".." in path_parts.parts
            or path_parts.parts[:2] != prefix
            or len(path_parts.parts) < 3
        ):
            raise ReleaseBuildError(f"unsafe tracked release path: {relative}")
        if object_type != b"blob" or mode not in {b"100644", b"100755"}:
            raise ReleaseBuildError(f"unsupported tracked release entry: {relative}")
        try:
            object_id = encoded_object_id.decode("ascii")
        except UnicodeDecodeError as error:
            raise ReleaseBuildError("tracked release object ID is invalid") from error
        if not _GIT_OBJECT_ID.fullmatch(object_id):
            raise ReleaseBuildError("tracked release object ID is invalid")
        source = root.joinpath(*path_parts.parts)
        try:
            if source.is_symlink():
                raise ReleaseBuildError(
                    f"release input must not contain symlinks: {relative}"
                )
            if not source.is_file():
                raise ReleaseBuildError(f"missing tracked release input: {relative}")
        except OSError as error:
            raise ReleaseBuildError(
                f"unable to inspect release input {relative}: {error}"
            ) from error
        files.append(
            TrackedBundleFile(
                relative,
                object_id,
                0o755 if mode == b"100755" else 0o644,
            )
        )
    if not files:
        raise ReleaseBuildError(f"domain bundle has no tracked files: {bundle_name}")
    return tuple(sorted(files, key=lambda item: item.path))


def _git_blob_bytes(
    root: Path, tracked_files: tuple[TrackedBundleFile, ...]
) -> dict[str, bytes]:
    """Read selected HEAD blobs in one stream, never from the mutable checkout."""
    object_ids = tuple(file.object_id for file in tracked_files)
    try:
        completed = subprocess.run(
            ("git", "-C", str(root), "cat-file", "--batch"),
            check=False,
            capture_output=True,
            input=("\n".join(object_ids) + "\n").encode("ascii"),
        )
    except OSError as error:
        raise ReleaseBuildError("unable to read tracked release input blobs") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ReleaseBuildError(f"unable to read tracked release input blobs: {detail}")

    blobs: dict[str, bytes] = {}
    offset = 0
    for tracked in tracked_files:
        header_end = completed.stdout.find(b"\n", offset)
        if header_end < 0:
            raise ReleaseBuildError("unable to parse tracked release input blobs")
        header = completed.stdout[offset:header_end].split()
        offset = header_end + 1
        if len(header) != 3:
            raise ReleaseBuildError("unable to parse tracked release input blobs")
        object_id, object_type, encoded_size = header
        try:
            size = int(encoded_size)
        except ValueError as error:
            raise ReleaseBuildError(
                "unable to parse tracked release input blobs"
            ) from error
        if (
            object_id.decode("ascii", errors="replace") != tracked.object_id
            or object_type != b"blob"
            or size < 0
            or offset + size >= len(completed.stdout)
        ):
            raise ReleaseBuildError("unable to parse tracked release input blobs")
        blobs[tracked.object_id] = completed.stdout[offset : offset + size]
        offset += size
        if completed.stdout[offset : offset + 1] != b"\n":
            raise ReleaseBuildError("unable to parse tracked release input blobs")
        offset += 1
    if offset != len(completed.stdout):
        raise ReleaseBuildError("unable to parse tracked release input blobs")
    return blobs


def _write_archive(
    destination: Path, version: str, records: tuple[FileRecord, ...]
) -> None:
    prefix = f"{_ARCHIVE_PREFIX}-{version}"
    temporary = _temporary_path(destination)
    try:
        with (
            temporary.open("wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
            tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
            ) as archive,
        ):
            for record in records:
                info = tarfile.TarInfo(f"{prefix}/{record.path}")
                info.size = len(record.data)
                info.mode = record.mode
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                archive.addfile(info, fileobj=_bytes_stream(record.data))
        os.replace(temporary, destination)
    except (OSError, tarfile.TarError) as error:
        temporary.unlink(missing_ok=True)
        raise ReleaseBuildError(f"unable to write release archive: {error}") from error


def _bytes_stream(data: bytes):
    from io import BytesIO

    return BytesIO(data)


def _release_document(
    *,
    archive_name: str,
    archive_base_url: str,
    archive_sha256: str,
    commit: str,
    contracts: tuple[BundleContract, ...],
    records: tuple[FileRecord, ...],
    version: str,
) -> dict[str, object]:
    if not _SHA256.fullmatch(archive_sha256):
        raise ReleaseBuildError("release archive checksum is invalid")
    bundle_metadata = {}
    for contract in contracts:
        name = contract.name
        bundle_metadata[name] = {
            "contract_schema_version": _contract_schema_version(
                next(
                    record
                    for record in records
                    if record.path == f"plugins/{name}/manifest-capabilities.yml"
                ).data,
                name,
            ),
            "sha256": _bundle_sha256(name, records),
            "version": contract.version,
        }
    return {
        "archive_sha256": archive_sha256,
        "archive_url": f"{archive_base_url}/{version}/{archive_name}",
        "bundles": bundle_metadata,
        "commit": commit,
        "files": {
            record.path: {
                "mode": format(record.mode, "04o"),
                "sha256": record.sha256,
                "size": len(record.data),
            }
            for record in records
        },
        "minimum_adapter_versions": _minimum_adapter_versions(),
        "schema_version": 1,
        "version": version,
    }


def _contract_schema_version(data: bytes, name: str) -> int:
    try:
        document = yaml.safe_load(data)
    except yaml.YAMLError as error:
        raise ReleaseBuildError(
            f"{name}: unable to parse contract schema version"
        ) from error
    schema_version = (
        document.get("schema_version") if isinstance(document, dict) else None
    )
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ReleaseBuildError(f"{name}: contract schema version is invalid")
    return schema_version


def _bundle_sha256(name: str, records: tuple[FileRecord, ...]) -> str:
    prefix = f"plugins/{name}/"
    digest = hashlib.sha256()
    bundle_records = [record for record in records if record.path.startswith(prefix)]
    if not bundle_records:
        raise ReleaseBuildError(f"{name}: release bundle has no files")
    for record in bundle_records:
        relative = record.path.removeprefix(prefix).encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(record.mode.to_bytes(2, "big"))
        digest.update(len(record.data).to_bytes(8, "big"))
        digest.update(bytes.fromhex(record.sha256))
    return digest.hexdigest()


def _minimum_adapter_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in AdapterRegistry.names():
        version = getattr(AdapterRegistry.create(name), "adapter_version", None)
        if not isinstance(version, str) or not version:
            raise ReleaseBuildError(f"{name}: adapter version is invalid")
        versions[name] = version
    return versions


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReleaseBuildError(f"unable to checksum {path}: {error}") from error
    return digest.hexdigest()


def _json_bytes(document: dict[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _temporary_path(destination: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    return Path(name)


def _write_bytes(destination: Path, data: bytes) -> None:
    temporary = _temporary_path(destination)
    try:
        temporary.write_bytes(data)
        os.replace(temporary, destination)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ReleaseBuildError(f"unable to write release metadata: {error}") from error


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="clean repository checkout to package",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.mkdtemp(prefix="manifest-release-")),
        help="directory for the archive and metadata (defaults outside the checkout)",
    )
    parser.add_argument(
        "--archive-base-url",
        required=True,
        help="credential-free HTTPS release base URL",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        release = build_release(args.repo_root, args.output_dir, args.archive_base_url)
    except ReleaseBuildError as error:
        print(f"build_manifest_release.py: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "archive": str(release.archive),
                "archive_sha256": release.archive_sha256,
                "commit": release.commit,
                "metadata": str(release.metadata),
                "version": release.version,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
