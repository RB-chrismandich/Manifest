"""Immutable local and published release acquisition."""

import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
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
_LOCAL_SELECTOR = re.compile(r"^local-([0-9a-f]{12})$")
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
    """Digest tracked and non-ignored checkout files in stable path order."""
    root = root.expanduser().resolve()
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
        _digest_checkout_entry(digest, root, relative, gitlinks.get(relative), runner)
    return digest.hexdigest()


def _digest_checkout_entry(
    digest: Any,
    root: Path,
    relative: str,
    gitlink_commit: str | None,
    runner: CommandRunner,
) -> None:
    path = root / relative
    encoded_path = relative.encode("utf-8", errors="surrogateescape")
    digest.update(len(encoded_path).to_bytes(8, "big"))
    digest.update(encoded_path)
    if gitlink_commit is not None:
        digest.update(b"g")
        digest.update(gitlink_commit.encode("ascii"))
        tree = _gitlink_tree_sha256(root, relative, gitlink_commit, runner, root)
        if tree is not None:
            digest.update(bytes.fromhex(tree))
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


def _gitlink_tree_sha256(
    repository: Path,
    relative: str,
    commit: str,
    runner: CommandRunner,
    worktree: Path | None,
    parent_commit: str | None = None,
) -> str | None:
    """Digest a recorded submodule tree, or None when no local objects hold it.

    A plain clone made without --recurse-submodules has neither a submodule
    checkout nor its objects. The gitlink commit already pins that content, so
    such a checkout stays digestible with the commit-only encoding.
    """
    path = worktree / relative if worktree is not None else None
    if path is not None and _is_git_checkout(path, runner):
        if _checkout_is_clean_at_commit(path, commit, runner):
            return _git_commit_tree_sha256(path, commit, runner, path)
        return deterministic_tree_sha256(path)

    object_repository = _find_submodule_repository(
        repository, parent_commit, commit, relative, runner
    )
    if object_repository is None:
        return None
    return _git_commit_tree_sha256(object_repository, commit, runner, None)


def _listed_git_tree(
    repository: Path, commit: str, runner: CommandRunner
) -> tuple[list[tuple[str, str, str, str]], dict[str, bytes]]:
    if not _git_commit_exists(repository, commit, runner):
        raise ReleaseError(f"unable to read recorded submodule tree at commit {commit}")
    listed = runner.run(
        (
            "git",
            "-C",
            str(repository),
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit,
        )
    )
    if listed.returncode != 0:
        raise ReleaseError(f"unable to read recorded submodule tree at commit {commit}")

    entries: list[tuple[str, str, str, str]] = []
    blob_ids: list[str] = []
    for item in listed.stdout.split("\0"):
        if not item:
            continue
        metadata, separator, relative = item.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise ReleaseError("unable to parse recorded submodule tree")
        mode, kind, object_id = fields
        if mode == "160000":
            if kind != "commit":
                raise ReleaseError("recorded submodule tree has an invalid gitlink")
        elif kind == "blob" and mode in {"100644", "100755", "120000"}:
            blob_ids.append(object_id)
        else:
            raise ReleaseError("recorded submodule tree has an unsupported entry")
        entries.append((relative, mode, kind, object_id))
    entries.sort(key=lambda entry: entry[0])
    return entries, _read_git_blobs(repository, blob_ids)


def _git_commit_tree_sha256(
    repository: Path,
    commit: str,
    runner: CommandRunner,
    worktree: Path | None,
) -> str:
    entries, blobs = _listed_git_tree(repository, commit, runner)
    digest = hashlib.sha256()
    for relative, mode, _kind, object_id in entries:
        encoded_path = relative.encode("utf-8", errors="surrogateescape")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        if mode == "160000":
            digest.update(b"g")
            digest.update(object_id.encode("ascii"))
            tree = _gitlink_tree_sha256(
                repository, relative, object_id, runner, worktree, commit
            )
            if tree is not None:
                digest.update(bytes.fromhex(tree))
        else:
            payload = blobs[object_id]
            if mode == "120000":
                digest.update(b"xl" + len(payload).to_bytes(8, "big") + payload)
            else:
                executable = b"x" if mode == "100755" else b"-"
                digest.update(
                    executable
                    + b"f"
                    + len(payload).to_bytes(8, "big")
                    + hashlib.sha256(payload).digest()
                )
    return digest.hexdigest()


def _verify_generated_views(root: Path, runner: CommandRunner) -> None:
    generator = root / "tools" / "generate_plugin_views.py"
    if not generator.is_file():
        raise ReleaseError("local source is missing the generated-view verifier")
    # The generator imports both this package (src) and manifest_model_policy
    # (configs/claude/scripts). Installing from a checkout runs under whatever
    # interpreter invoked us — in live parity that is a bare `uvx --from
    # <wheel>` environment — so the child is handed the checkout's own import
    # roots rather than inheriting a developer venv's site-packages.
    python_path = os.pathsep.join(
        (str(root / "src"), str(root / "configs" / "claude" / "scripts"))
    )
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


def _read_git_blobs(repository: Path, object_ids: list[str]) -> dict[str, bytes]:
    requested = list(dict.fromkeys(object_ids))
    if not requested:
        return {}
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), "cat-file", "--batch"),
            input=("".join(f"{object_id}\n" for object_id in requested)).encode(
                "ascii"
            ),
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise ReleaseError("unable to read recorded submodule tree blobs") from error
    if completed.returncode != 0:
        raise ReleaseError("unable to read recorded submodule tree blobs")

    output = completed.stdout
    position = 0
    blobs: dict[str, bytes] = {}
    for object_id in requested:
        header_end = output.find(b"\n", position)
        if header_end < 0:
            raise ReleaseError("recorded submodule tree blob output is incomplete")
        fields = output[position:header_end].split()
        if (
            len(fields) != 3
            or fields[0].decode("ascii", errors="replace") != object_id
            or fields[1] != b"blob"
        ):
            raise ReleaseError("recorded submodule tree contains an unreadable blob")
        try:
            size = int(fields[2])
        except ValueError as error:
            raise ReleaseError(
                "recorded submodule tree blob size is invalid"
            ) from error
        start = header_end + 1
        end = start + size
        if end >= len(output) or output[end : end + 1] != b"\n":
            raise ReleaseError("recorded submodule tree blob output is incomplete")
        blobs[object_id] = output[start:end]
        position = end + 1
    if position != len(output):
        raise ReleaseError("recorded submodule tree blob output has trailing data")
    return blobs


def _find_submodule_repository(
    repository: Path,
    parent_commit: str | None,
    commit: str,
    relative: str,
    runner: CommandRunner,
) -> Path | None:
    common_dir_result = runner.run(
        ("git", "-C", str(repository), "rev-parse", "--git-common-dir")
    )
    common_dir: Path | None = None
    if common_dir_result.returncode == 0:
        common_dir = Path(common_dir_result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = repository / common_dir
        common_dir = common_dir.resolve()
    elif (repository / "objects").is_dir() and (repository / "HEAD").is_file():
        common_dir = repository.resolve()

    module_name = _submodule_name(repository, parent_commit, relative, runner)
    candidates: list[Path] = []
    if common_dir is not None:
        if module_name is not None:
            candidates.append(common_dir / "modules" / module_name)
        candidates.append(common_dir / "modules" / relative)
    candidates.append(repository)
    for candidate in candidates:
        if _git_commit_exists(candidate, commit, runner):
            return candidate
    return None


def _submodule_name(
    repository: Path,
    parent_commit: str | None,
    relative: str,
    runner: CommandRunner,
) -> str | None:
    gitmodules = repository / ".gitmodules"
    if gitmodules.is_file():
        config_args = ("--file", str(gitmodules))
    else:
        if parent_commit is None:
            head = runner.run(("git", "-C", str(repository), "rev-parse", "HEAD"))
            if head.returncode != 0:
                return None
            parent_commit = head.stdout.strip()
        config_args = ("--blob", f"{parent_commit}:.gitmodules")
    result = runner.run(
        (
            "git",
            "-C",
            str(repository),
            "config",
            *config_args,
            "--get-regexp",
            r"^submodule\..*\.path$",
        )
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(" ")
        if (
            separator
            and value == relative
            and key.startswith("submodule.")
            and key.endswith(".path")
        ):
            return key[len("submodule.") : -len(".path")]
    return None


def _git_commit_exists(repository: Path, commit: str, runner: CommandRunner) -> bool:
    result = runner.run(
        ("git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}")
    )
    return result.returncode == 0


def _is_git_checkout(path: Path, runner: CommandRunner) -> bool:
    if not path.is_dir() or not (path / ".git").exists():
        return False
    result = runner.run(("git", "-C", str(path), "rev-parse", "--show-toplevel"))
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == path.resolve()
    except OSError:
        return False


def _checkout_is_clean_at_commit(
    path: Path, commit: str, runner: CommandRunner
) -> bool:
    head = runner.run(("git", "-C", str(path), "rev-parse", "HEAD"))
    if head.returncode != 0 or head.stdout.strip().lower() != commit.lower():
        return False
    status = runner.run(
        (
            "git",
            "-C",
            str(path),
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
    )
    return status.returncode == 0 and not status.stdout


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


def _validate_local_source(
    prefix: str, source_commit: str | None, source_checkout: Path | None
) -> tuple[Path, str, CommandRunner]:
    if source_commit is None or source_checkout is None:
        raise ReleaseError(
            "local release selector requires source_commit and source_checkout"
        )
    if not isinstance(source_commit, str) or not _COMMIT.fullmatch(source_commit):
        raise ReleaseError("local release source_commit must be a full immutable SHA")
    commit = source_commit.lower()
    if not commit.startswith(prefix):
        raise ReleaseError("local release selector does not match source_commit")
    if not isinstance(source_checkout, Path):
        raise ReleaseError("local release source_checkout must be a Git checkout path")
    source = source_checkout.expanduser().resolve()
    runner = CommandRunner()
    if not _is_git_checkout(source, runner):
        raise ReleaseError(
            f"local release source_checkout is not a Git checkout: {source}"
        )
    if not _git_commit_exists(source, commit, runner):
        raise ReleaseError(
            f"local source checkout does not contain source_commit {commit}"
        )
    return source, commit, runner


def _open_local_cache_lock(cache_root: Path, commit: str) -> tuple[int, Path]:
    lock_path = cache_root / f".local-{commit}.lock"
    descriptor = -1
    try:
        cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise ReleaseError("unable to prepare or lock local release cache") from error
    return descriptor, cache_root / f"local-{commit}"


def _initialize_local_submodules(
    source: Path, cache: Path, commit: str, runner: CommandRunner
) -> None:
    listed = runner.run(("git", "-C", str(cache), "ls-files", "-s", "-z"))
    if listed.returncode != 0:
        raise ReleaseError("unable to inspect cached local release submodules")
    gitlinks = _gitlink_commits(listed.stdout)
    if not gitlinks:
        return

    sources: dict[str, Path] = {}
    for relative, subcommit in gitlinks.items():
        source_repository = _find_submodule_repository(
            source, commit, subcommit, relative, runner
        )
        module_name = _submodule_name(cache, commit, relative, runner)
        if source_repository is None or module_name is None:
            raise ReleaseError(
                "unable to initialize cached local release submodules: "
                f"local objects unavailable for {relative!r} at {subcommit}"
            )
        configured = runner.run(
            (
                "git",
                "-C",
                str(cache),
                "config",
                f"submodule.{module_name}.url",
                str(source_repository),
            )
        )
        if configured.returncode != 0:
            raise ReleaseError(
                f"unable to configure local release submodule {relative!r}"
            )
        sources[relative] = source_repository

    result = runner.run(
        (
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(cache),
            "submodule",
            "update",
            "--init",
            "--",
            *gitlinks,
        )
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseError(
            f"unable to initialize cached local release submodules: {detail}"
        )
    for relative, subcommit in gitlinks.items():
        _initialize_local_submodules(
            sources[relative], cache / relative, subcommit, runner
        )


def _create_local_cache(
    source: Path,
    commit: str,
    destination: Path,
    cache_root: Path,
    runner: CommandRunner,
) -> ResolvedRelease:
    temporary = Path(tempfile.mkdtemp(prefix=f".local-{commit}.", dir=cache_root))
    try:
        cloned = runner.run(
            (
                "git",
                "clone",
                "--local",
                "--no-hardlinks",
                "--no-checkout",
                str(source),
                str(temporary),
            )
        )
        if cloned.returncode != 0:
            detail = cloned.stderr.strip() or cloned.stdout.strip()
            raise ReleaseError(
                "unable to materialize local release checkout"
                + (f": {detail}" if detail else "")
            )
        checked_out = runner.run(
            ("git", "-C", str(temporary), "checkout", "--detach", commit)
        )
        if checked_out.returncode != 0:
            detail = checked_out.stderr.strip() or checked_out.stdout.strip()
            raise ReleaseError(
                f"unable to check out local source_commit {commit}"
                + (f": {detail}" if detail else "")
            )
        _initialize_local_submodules(source, temporary, commit, runner)
        _validate_local_cache(temporary, commit)
        if destination.is_symlink() or destination.exists():
            raise ReleaseError("local release cache entry appeared during creation")
        os.replace(temporary, destination)
        return _validate_local_cache(destination, commit)
    except OSError as error:
        raise ReleaseError("unable to materialize local release cache") from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _resolve_local_commit(
    prefix: str,
    source_commit: str | None,
    source_checkout: Path | None,
) -> ResolvedRelease:
    source, commit, runner = _validate_local_source(
        prefix, source_commit, source_checkout
    )
    cache_root = xdg_paths().cache / "releases"
    descriptor, destination = _open_local_cache_lock(cache_root, commit)
    try:
        if destination.is_symlink():
            raise ReleaseError("cached local release entry must not be a symlink")
        if destination.exists():
            return _validate_local_cache(destination, commit)
        return _create_local_cache(source, commit, destination, cache_root, runner)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _validate_local_cache(root: Path, commit: str) -> ResolvedRelease:
    try:
        release = _resolve_local(root)
    except ReleaseError as error:
        raise ReleaseError(f"cached local release is invalid: {error}") from error
    if release.source_commit.lower() != commit:
        raise ReleaseError("cached local release HEAD does not match source_commit")
    if release.source_dirty:
        raise ReleaseError("cached local release checkout is not clean")

    runner = CommandRunner()
    symbolic_head = runner.run(
        ("git", "-C", str(root), "symbolic-ref", "--quiet", "HEAD")
    )
    if symbolic_head.returncode == 0:
        raise ReleaseError("cached local release checkout is not detached")
    if symbolic_head.returncode != 1:
        raise ReleaseError("unable to validate cached local release HEAD")

    submodules = runner.run(
        ("git", "-C", str(root), "submodule", "status", "--recursive")
    )
    if submodules.returncode != 0 or any(
        line and line[0] != " " for line in submodules.stdout.splitlines()
    ):
        raise ReleaseError(
            "cached local release submodules are not initialized cleanly"
        )
    return release


def resolve_release(
    selector: str | Path,
    *,
    source_commit: str | None = None,
    source_checkout: Path | None = None,
) -> ResolvedRelease:
    """Resolve a checkout, receipt-pinned local release, or published version."""
    if isinstance(selector, Path):
        return _resolve_local(selector)
    if not isinstance(selector, str) or not selector.strip():
        raise ReleaseError("release selector must be a local path or immutable version")

    local_selector = _LOCAL_SELECTOR.fullmatch(selector)
    if local_selector is not None:
        return _resolve_local_commit(
            local_selector.group(1), source_commit, source_checkout
        )
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

    _verify_generated_views(root, runner)

    status_result = runner.run(
        (
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
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
