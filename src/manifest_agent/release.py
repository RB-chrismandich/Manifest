"""Immutable local and published release acquisition."""

import hashlib
import hmac
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from manifest_agent.models import MarketplaceSource, MarketplaceSourceKind
from manifest_agent.paths import xdg_paths
from manifest_agent.process import CommandRunner

REPOSITORY_URL = "https://github.com/RB-chrismandich/Manifest"
RELEASE_INDEX_URL = (
    REPOSITORY_URL + "/releases/download/{version}/manifest-release.json"
)
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_MUTABLE_URL_PART = re.compile(r"/(?:main|master|develop|trunk|head)(?:/|$)", re.I)


class ReleaseError(RuntimeError):
    """A release was mutable, malformed, unavailable, or failed verification."""


@dataclass(frozen=True)
class ResolvedRelease:
    """Verified immutable release identity and its local content root."""

    version: str
    source_commit: str
    source: str
    marketplace_source: MarketplaceSource
    release_root: Path
    repository_url: str
    source_dirty: bool
    archive_sha256: str


def verify_sha256(path: Path, expected: str) -> str:
    """Verify a file against a strict hexadecimal SHA-256 checksum."""
    if not _SHA256.fullmatch(expected):
        raise ReleaseError("release metadata SHA-256 is invalid")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise ReleaseError(f"unable to read release archive: {error}") from error
    actual = digest.hexdigest()
    if not _constant_time_equal(actual, expected.lower()):
        raise ReleaseError("release archive checksum mismatch")
    return actual


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def deterministic_tree_sha256(root: Path) -> str:
    """Digest all tracked and non-ignored checkout files in stable path order."""
    runner = CommandRunner()
    result = runner.run(
        (
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        )
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"unable to inventory local checkout: {result.stderr.strip()}"
        )

    deleted = runner.run(("git", "-C", str(root), "ls-files", "-z", "--deleted"))
    if deleted.returncode != 0:
        raise ReleaseError("unable to inspect deleted local checkout entries")
    deleted_paths = {path for path in deleted.stdout.split("\0") if path}

    staged = runner.run(("git", "-C", str(root), "ls-files", "-s", "-z"))
    if staged.returncode != 0:
        raise ReleaseError("unable to inspect local checkout entries")
    gitlinks = _gitlink_commits(staged.stdout)

    digest = hashlib.sha256()
    relative_paths = sorted(
        path for path in result.stdout.split("\0") if path and path not in deleted_paths
    )
    for relative in relative_paths:
        _digest_checkout_entry(digest, root, relative, gitlinks.get(relative))
    return digest.hexdigest()


def _digest_checkout_entry(
    digest: Any, root: Path, relative: str, gitlink_commit: str | None
) -> None:
    path = root / relative
    encoded_path = relative.encode("utf-8", errors="surrogateescape")
    digest.update(len(encoded_path).to_bytes(8, "big"))
    digest.update(encoded_path)
    if gitlink_commit is not None:
        digest.update(b"g")
        digest.update(gitlink_commit.encode("ascii"))
        # Recurse only into a submodule that is genuinely initialized. An
        # uninitialized gitlink leaves an empty directory that is not its own
        # repository, so `git -C <dir> ls-files` resolves to the PARENT repo
        # and returns this very gitlink back as "./" -- which lands here again
        # for the same path, forever. Measured on this repository: an empty
        # tests/test_helper/bats-assert yields `160000 <sha> 0 ./`, and the
        # digest recursed until RecursionError. Any clone made without
        # --recurse-submodules reproduces it, CI images included.
        if path.is_dir() and (path / ".git").exists():
            digest.update(bytes.fromhex(deterministic_tree_sha256(path)))
        return
    try:
        metadata = path.lstat()
        digest.update(b"x" if metadata.st_mode & 0o111 else b"-")
        if path.is_symlink():
            payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
            digest.update(b"l" + len(payload).to_bytes(8, "big") + payload)
            return
        if path.is_file():
            size, file_digest = _file_sha256(path)
            digest.update(b"f" + size.to_bytes(8, "big") + file_digest)
            return
    except OSError as error:
        raise ReleaseError(
            f"unable to digest local checkout path {relative!r}"
        ) from error
    raise ReleaseError(f"unsupported checkout entry type: {relative}")


def _file_sha256(path: Path) -> tuple[int, bytes]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.digest()


def _gitlink_commits(output: str) -> dict[str, str]:
    gitlinks: dict[str, str] = {}
    for entry in output.split("\0"):
        if not entry:
            continue
        metadata, separator, relative = entry.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise ReleaseError("unable to parse local checkout entries")
        mode, object_id, _stage = fields
        if mode == "160000":
            gitlinks[relative] = object_id
    return gitlinks


def resolve_release(selector: str | Path) -> ResolvedRelease:
    """Resolve an existing checkout path or an immutable published version."""
    if isinstance(selector, Path):
        return _resolve_local(selector)
    if not isinstance(selector, str) or not selector.strip():
        raise ReleaseError("release selector must be a local path or immutable version")

    candidate = Path(selector).expanduser()
    if candidate.exists() or selector.startswith((".", "~", "/")):
        return _resolve_local(candidate)
    if not _VERSION.fullmatch(selector):
        raise ReleaseError("published release selector must be an immutable version")
    return _resolve_published(selector)


def _resolve_local(candidate: Path) -> ResolvedRelease:
    root = candidate.expanduser().resolve()
    if not root.is_dir() or not (root / ".git").exists():
        raise ReleaseError(f"local source is not a git checkout: {root}")
    runner = CommandRunner()
    head = runner.run(("git", "-C", str(root), "rev-parse", "HEAD"))
    if head.returncode != 0 or not _COMMIT.fullmatch(head.stdout.strip()):
        raise ReleaseError("unable to resolve immutable local checkout HEAD")
    commit = head.stdout.strip().lower()

    generator = root / "tools" / "generate_plugin_views.py"
    if not generator.is_file():
        raise ReleaseError("local source is missing the generated-view verifier")
    python_path = str(root / "src")
    if inherited_python_path := os.environ.get("PYTHONPATH"):
        python_path += os.pathsep + inherited_python_path
    generated = runner.run(
        (
            sys.executable,
            str(generator),
            "--check",
            "--repo-root",
            str(root),
        ),
        env={"PYTHONPATH": python_path},
    )
    if generated.returncode != 0:
        raise ReleaseError("local source generated views are not clean")

    status_result = runner.run(
        ("git", "-C", str(root), "status", "--porcelain", "--untracked-files=all")
    )
    if status_result.returncode != 0:
        raise ReleaseError("unable to inspect local checkout status")
    return ResolvedRelease(
        version=f"local-{commit[:12]}",
        source_commit=commit,
        source=str(root),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(root), None
        ),
        release_root=root,
        repository_url=REPOSITORY_URL,
        source_dirty=bool(status_result.stdout),
        archive_sha256=deterministic_tree_sha256(root),
    )


def _resolve_published(version: str) -> ResolvedRelease:
    index_url = RELEASE_INDEX_URL.format(version=version)
    metadata = _download_json(index_url)
    commit, archive_url, checksum = _validate_index(version, metadata)

    cache = xdg_paths().cache / "releases" / f"{version}-{checksum[:16]}"
    archive = cache.parent / f"{version}-{checksum[:16]}.tar.gz"
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not archive.exists():
        _download_file(archive_url, archive)
    verify_sha256(archive, checksum)
    if cache.exists():
        _verify_extracted_cache(archive, cache)
    else:
        _extract_archive_atomic(archive, cache)
    release_root = _content_root(cache)
    if not (release_root / "plugins").is_dir():
        raise ReleaseError("published release archive is missing the plugins directory")
    return ResolvedRelease(
        version=version,
        source_commit=commit,
        source=index_url,
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.GIT, f"{REPOSITORY_URL}.git", commit
        ),
        release_root=release_root,
        repository_url=REPOSITORY_URL,
        source_dirty=False,
        archive_sha256=checksum,
    )


def _download_json(url: str) -> dict[str, object]:
    try:
        with urlopen(
            Request(url, headers={"Accept": "application/json"}), timeout=30
        ) as response:
            document = json.load(response)
    except (OSError, ValueError) as error:
        raise ReleaseError("unable to load published release metadata") from error
    if not isinstance(document, dict):
        raise ReleaseError("published release metadata must be a JSON object")
    return document


def _validate_index(version: str, metadata: dict[str, object]) -> tuple[str, str, str]:
    indexed_version = metadata.get("version")
    commit = metadata.get("commit")
    archive_url = metadata.get("archive_url")
    checksum = metadata.get("archive_sha256")
    if indexed_version != version:
        raise ReleaseError("release index version does not match requested version")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ReleaseError("release index commit must be an immutable full SHA")
    if not isinstance(archive_url, str):
        raise ReleaseError("release index archive URL is required")
    parsed = urlparse(archive_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ReleaseError("release archive URL must be credential-free HTTPS")
    if _MUTABLE_URL_PART.search(parsed.path):
        raise ReleaseError("release archive URL contains a mutable branch identity")
    if not isinstance(checksum, str) or not _SHA256.fullmatch(checksum):
        raise ReleaseError("release index archive SHA-256 is invalid")
    return commit.lower(), archive_url, checksum.lower()


def _download_file(url: str, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            with urlopen(Request(url), timeout=60) as response:
                shutil.copyfileobj(response, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise ReleaseError("unable to download published release archive") from error


def _extract_archive_atomic(archive: Path, destination: Path) -> None:
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        with tarfile.open(archive, "r:*") as bundle:
            for member in bundle.getmembers():
                member_path = PurePosixPath(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or member.issym()
                    or member.islnk()
                    or member.isdev()
                ):
                    raise ReleaseError("release archive contains an unsafe path")
                target = temporary.joinpath(*member_path.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        raise ReleaseError(
                            "release archive contains an unreadable file"
                        )
                    with source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(member.mode & 0o777)
                else:
                    raise ReleaseError("release archive contains an unsupported entry")
        os.replace(temporary, destination)
    except (OSError, tarfile.TarError) as error:
        raise ReleaseError("unable to extract published release archive") from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _verify_extracted_cache(archive: Path, cache: Path) -> None:
    verification_parent = Path(
        tempfile.mkdtemp(prefix=f".{cache.name}.verify.", dir=cache.parent)
    )
    fresh = verification_parent / "release"
    try:
        _extract_archive_atomic(archive, fresh)
        expected = _directory_content_sha256(fresh)
        actual = _directory_content_sha256(cache)
        if not hmac.compare_digest(actual, expected):
            raise ReleaseError("published release cache integrity check failed")
    finally:
        shutil.rmtree(verification_parent, ignore_errors=True)


def _directory_content_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    try:
        paths = sorted(
            root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()
        )
        for path in paths:
            relative = path.relative_to(root).as_posix().encode()
            digest.update(len(relative).to_bytes(8, "big") + relative)
            if path.is_symlink():
                raise ReleaseError("published release cache integrity check failed")
            if path.is_dir():
                digest.update(b"d")
                continue
            if not path.is_file():
                raise ReleaseError("published release cache integrity check failed")
            metadata = path.stat()
            size, file_digest = _file_sha256(path)
            executable = b"x" if metadata.st_mode & 0o111 else b"-"
            digest.update(b"f" + executable + size.to_bytes(8, "big") + file_digest)
    except OSError as error:
        raise ReleaseError("published release cache integrity check failed") from error
    return digest.hexdigest()


def _content_root(extracted: Path) -> Path:
    children = tuple(extracted.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extracted
