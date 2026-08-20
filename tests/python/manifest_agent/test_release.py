import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from manifest_agent.models import MarketplaceSourceKind
from manifest_agent.release import (
    RELEASE_INDEX_URL,
    REPOSITORY_URL,
    ReleaseError,
    deterministic_tree_sha256,
    resolve_release,
    verify_sha256,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _local_checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    (repo / "tools").mkdir()
    (repo / "plugins").mkdir()
    (repo / "plugins" / "bundle.txt").write_text("portable\n", encoding="utf-8")
    (repo / "tools" / "generate_plugin_views.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[sys.argv.index('--repo-root') + 1])\n"
        "expected = Path(__file__).resolve().parents[1]\n"
        "raise SystemExit(0 if '--check' in sys.argv and root == expected else 2)\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "manifest@example.invalid")
    _git(repo, "config", "user.name", "Manifest Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _release_archive(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "manifest-release.tar.gz"
    payload = b"portable\n"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("manifest-1.2.3/plugins/bundle.txt")
        info.size = len(payload)
        info.mtime = 0
        tar.addfile(info, io.BytesIO(payload))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    return archive, checksum


def test_checksum_mismatch_blocks_release(tmp_path):
    archive = tmp_path / "release.tgz"
    archive.write_bytes(b"tampered")

    with pytest.raises(ReleaseError, match="checksum mismatch"):
        verify_sha256(archive, "0" * 64)


def test_local_checkout_records_head_dirty_and_deterministic_digest(tmp_path):
    repo = _local_checkout(tmp_path)
    expected_head = _git(repo, "rev-parse", "HEAD")

    release = resolve_release(repo)

    assert release.version == f"local-{expected_head[:12]}"
    assert release.source_commit == expected_head
    assert release.source_dirty is False
    assert release.archive_sha256 == deterministic_tree_sha256(repo)
    assert release.release_root == repo.resolve()
    assert release.marketplace_source.kind is MarketplaceSourceKind.LOCAL
    assert release.marketplace_source.source == str(repo.resolve())
    assert release.marketplace_source.ref is None


def test_local_checkout_digest_and_dirty_flag_detect_uncommitted_drift(tmp_path):
    repo = _local_checkout(tmp_path)
    clean = resolve_release(repo)
    (repo / "plugins" / "bundle.txt").write_text("changed\n", encoding="utf-8")

    dirty = resolve_release(repo)

    assert dirty.source_dirty is True
    assert dirty.source_commit == clean.source_commit
    assert dirty.archive_sha256 != clean.archive_sha256


def test_local_checkout_digest_excludes_tracked_worktree_deletions(tmp_path):
    repo = _local_checkout(tmp_path)
    clean = deterministic_tree_sha256(repo)
    (repo / "plugins" / "bundle.txt").unlink()

    dirty = resolve_release(repo)

    assert dirty.source_dirty is True
    assert dirty.archive_sha256 != clean


def test_local_checkout_digest_encodes_uninitialized_gitlinks(tmp_path):
    repo = _local_checkout(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},vendor/dependency",
    )

    assert len(deterministic_tree_sha256(repo)) == 64


def test_uninitialized_gitlink_with_an_empty_directory_does_not_recurse(tmp_path):
    """The gitlink directory exists but is empty -- what a plain clone leaves.

    The sibling test above registers a gitlink whose directory was never
    created, so `path.is_dir()` is False and the digest never descends. A clone
    made without --recurse-submodules is different: git materializes the path as
    an empty directory. That directory is not its own repository, so
    `git -C <dir> ls-files` resolves to the PARENT repo and hands back this very
    gitlink as "./", which re-enters the same path until RecursionError.
    """
    repo = _local_checkout(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    (repo / "vendor").mkdir(parents=True, exist_ok=True)
    (repo / "vendor" / "dependency").mkdir()
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},vendor/dependency",
    )

    assert len(deterministic_tree_sha256(repo)) == 64


def test_initialized_gitlink_still_contributes_its_tree(tmp_path):
    """A real nested checkout must still move the parent digest when it changes."""
    repo = _local_checkout(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    nested = repo / "vendor" / "dependency"
    nested.mkdir(parents=True)
    _git(nested, "init", "-q")
    (nested / "inner.txt").write_text("one\n", encoding="utf-8")
    _git(nested, "add", "inner.txt")
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},vendor/dependency",
    )

    before = deterministic_tree_sha256(repo)
    (nested / "inner.txt").write_text("two\n", encoding="utf-8")

    assert deterministic_tree_sha256(repo) != before


def test_local_checkout_requires_clean_generated_views(tmp_path):
    repo = _local_checkout(tmp_path)
    (repo / "tools" / "generate_plugin_views.py").write_text(
        "raise SystemExit(1)\n", encoding="utf-8"
    )

    with pytest.raises(ReleaseError, match="generated views are not clean"):
        resolve_release(repo)


@pytest.mark.parametrize("selector", ["main", "master", "develop", "feature/topic"])
def test_mutable_release_selectors_are_rejected(selector):
    with pytest.raises(ReleaseError, match="immutable version"):
        resolve_release(selector)


def test_published_release_validates_index_and_archive(monkeypatch, tmp_path):
    archive, checksum = _release_archive(tmp_path)
    commit = "a" * 40
    archive_url = "https://example.invalid/releases/1.2.3/manifest-release.tar.gz"
    index = {
        "version": "1.2.3",
        "commit": commit,
        "archive_url": archive_url,
        "archive_sha256": checksum,
    }
    requested_urls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout):
        url = request.full_url
        requested_urls.append((url, timeout))
        if url == RELEASE_INDEX_URL.format(version="1.2.3"):
            return Response(json.dumps(index).encode())
        if url == archive_url:
            return Response(archive.read_bytes())
        raise AssertionError(url)

    monkeypatch.setattr("manifest_agent.release.urlopen", fake_urlopen)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    release = resolve_release("1.2.3")

    assert release.version == "1.2.3"
    assert release.source_commit == commit
    assert release.source_dirty is False
    assert release.archive_sha256 == checksum
    assert release.marketplace_source.kind is MarketplaceSourceKind.GIT
    assert release.marketplace_source.source == f"{REPOSITORY_URL}.git"
    assert release.marketplace_source.ref == commit
    assert (release.release_root / "plugins" / "bundle.txt").read_text() == "portable\n"
    assert requested_urls[0][0] == RELEASE_INDEX_URL.format(version="1.2.3")


def test_published_release_rejects_tampered_extracted_cache(monkeypatch, tmp_path):
    archive, checksum = _release_archive(tmp_path)
    archive_url = "https://example.invalid/releases/1.2.3/manifest-release.tar.gz"
    index = {
        "version": "1.2.3",
        "commit": "a" * 40,
        "archive_url": archive_url,
        "archive_sha256": checksum,
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout):
        if request.full_url == RELEASE_INDEX_URL.format(version="1.2.3"):
            return Response(json.dumps(index).encode())
        if request.full_url == archive_url:
            return Response(archive.read_bytes())
        raise AssertionError(request.full_url)

    monkeypatch.setattr("manifest_agent.release.urlopen", fake_urlopen)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    release = resolve_release("1.2.3")
    (release.release_root / "plugins" / "bundle.txt").write_text(
        "tampered\n", encoding="utf-8"
    )

    with pytest.raises(ReleaseError, match="cache integrity"):
        resolve_release("1.2.3")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": "9.9.9"}, "version does not match"),
        ({"commit": "main"}, "commit"),
        ({"archive_url": "https://example.invalid/main/archive.tgz"}, "mutable"),
        ({"archive_sha256": "bad"}, "SHA-256"),
    ],
)
def test_published_release_rejects_invalid_metadata(monkeypatch, change, message):
    metadata = {
        "version": "1.2.3",
        "commit": "a" * 40,
        "archive_url": "https://example.invalid/releases/1.2.3/archive.tgz",
        "archive_sha256": "0" * 64,
    }
    metadata.update(change)

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        "manifest_agent.release.urlopen",
        lambda request, timeout: Response(json.dumps(metadata).encode()),
    )

    with pytest.raises(ReleaseError, match=message):
        resolve_release("1.2.3")
