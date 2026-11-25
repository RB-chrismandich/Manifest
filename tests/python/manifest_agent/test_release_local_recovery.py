"""Receipt-pinned local release and checksum recovery behavior tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from manifest_agent.release import (
    ReleaseError,
    deterministic_tree_sha256,
    resolve_release,
)
from manifest_agent.service_state import _tree_checksum
from tests.python.manifest_agent._release_test_helpers import _git, _local_checkout


def _local_checkout_with_submodule(tmp_path: Path) -> Path:
    repo = _local_checkout(tmp_path)
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    _git(dependency, "init")
    _git(dependency, "config", "user.email", "manifest@example.invalid")
    _git(dependency, "config", "user.name", "Manifest Test")
    (dependency / "inner.txt").write_text("submodule\n", encoding="utf-8")
    _git(dependency, "add", "inner.txt")
    _git(dependency, "commit", "-m", "dependency")
    _git(repo, "config", "protocol.file.allow", "always")
    _git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(dependency),
        "vendor/dependency",
    )
    url_entry = _git(
        repo, "config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.url$"
    )
    url_key = url_entry.split(maxsplit=1)[0]
    _git(
        repo,
        "config",
        "--file",
        ".gitmodules",
        url_key,
        "https://example.invalid/dependency.git",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add dependency")
    return repo


def test_gitlink_digest_is_stable_across_submodule_initialization(tmp_path):
    repo = _local_checkout_with_submodule(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    index_tree = _git(repo, "write-tree")
    submodule = repo / "vendor" / "dependency"
    submodule_head = _git(submodule, "rev-parse", "HEAD")

    initialized = deterministic_tree_sha256(repo)

    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "write-tree") == index_tree
    assert _git(submodule, "rev-parse", "HEAD") == submodule_head

    _git(repo, "submodule", "deinit", "-f", "vendor/dependency")
    uninitialized = deterministic_tree_sha256(repo)

    assert uninitialized == initialized
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "write-tree") == index_tree


def test_local_release_cache_identity_matches_initialized_and_uninitialized_source(
    monkeypatch, tmp_path
):
    repo = _local_checkout_with_submodule(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    submodule = repo / "vendor" / "dependency"
    source_before = (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "write-tree"),
        _git(repo, "submodule", "status", "--recursive"),
        _git(submodule, "rev-parse", "HEAD"),
    )
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "initialized-cache"))
    initialized = resolve_release(
        f"local-{commit[:12]}", source_commit=commit, source_checkout=repo
    )
    assert source_before == (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "write-tree"),
        _git(repo, "submodule", "status", "--recursive"),
        _git(submodule, "rev-parse", "HEAD"),
    )

    _git(repo, "submodule", "deinit", "-f", "vendor/dependency")
    deinitialized_before = (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "write-tree"),
        _git(repo, "submodule", "status", "--recursive"),
    )
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "deinitialized-cache"))
    uninitialized = resolve_release(
        f"local-{commit[:12]}", source_commit=commit, source_checkout=repo
    )

    assert uninitialized.version == initialized.version
    assert uninitialized.archive_sha256 == initialized.archive_sha256
    assert deinitialized_before == (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "write-tree"),
        _git(repo, "submodule", "status", "--recursive"),
    )
    assert not submodule.exists() or not (submodule / ".git").exists()


@pytest.mark.parametrize(
    "corruption", ["wrong_head", "dirty_content", "generated_view"]
)
def test_receipt_pinned_local_release_rejects_invalid_existing_worktree_cache(
    monkeypatch, tmp_path, corruption
):
    repo = _local_checkout(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    cached = resolve_release(
        f"local-{commit[:12]}", source_commit=commit, source_checkout=repo
    ).release_root

    if corruption == "wrong_head":
        (cached / "plugins" / "bundle.txt").write_text(
            "wrong cached head\n", encoding="utf-8"
        )
        _git(cached, "add", "plugins/bundle.txt")
        _git(cached, "commit", "-m", "wrong cached head")
    elif corruption == "dirty_content":
        (cached / "plugins" / "bundle.txt").write_text(
            "tampered cached bundle\n", encoding="utf-8"
        )
    else:
        (cached / "tools" / "generate_plugin_views.py").write_text(
            "raise SystemExit(1)\n", encoding="utf-8"
        )
        _git(cached, "add", "tools/generate_plugin_views.py")
        _git(cached, "commit", "-m", "invalid generated view validator")

    expected_errors = {
        "wrong_head": "cached local release HEAD does not match source_commit",
        "dirty_content": "cached local release checkout is not clean",
        "generated_view": (
            "cached local release is invalid: local source generated views are not clean"
        ),
    }
    with pytest.raises(ReleaseError, match=expected_errors[corruption]):
        resolve_release(
            f"local-{commit[:12]}", source_commit=commit, source_checkout=repo
        )


def test_receipt_pinned_local_release_materializes_and_reuses_detached_cache(
    monkeypatch, tmp_path
):
    repo = _local_checkout_with_submodule(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    (repo / "plugins" / "bundle.txt").write_text("newer source\n", encoding="utf-8")
    _git(repo, "add", "plugins/bundle.txt")
    _git(repo, "commit", "-m", "advance source")
    submodule = repo / "vendor" / "dependency"
    source_before = (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "write-tree"),
        _git(repo, "submodule", "status", "--recursive"),
        _git(submodule, "rev-parse", "HEAD"),
    )
    assert _git(repo, "rev-parse", "HEAD") != commit
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")

    release = resolve_release(
        f"local-{commit[:12]}",
        source_commit=commit,
        source_checkout=repo,
    )
    cached = release.release_root
    second = resolve_release(
        f"local-{commit[:12]}",
        source_commit=commit,
        source_checkout=repo,
    )

    assert cached == tmp_path / "xdg" / "manifest" / "releases" / f"local-{commit}"
    assert cached != repo.resolve()
    assert second.release_root == cached
    assert release.source_commit == commit
    assert release.source_dirty is False
    assert _git(cached, "rev-parse", "HEAD") == commit
    assert (cached / "plugins" / "bundle.txt").read_text(
        encoding="utf-8"
    ) == "portable\n"
    detached = subprocess.run(
        ("git", "-C", str(cached), "symbolic-ref", "--quiet", "HEAD"),
        capture_output=True,
        check=False,
    )
    assert detached.returncode == 1
    submodule_status = _git(cached, "submodule", "status", "--recursive")
    assert not submodule_status.startswith(("-", "+", "U"))
    assert source_before == (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "write-tree"),
        _git(repo, "submodule", "status", "--recursive"),
        _git(submodule, "rev-parse", "HEAD"),
    )


def test_receipt_pinned_local_release_rejects_bad_provenance_and_cache(
    monkeypatch, tmp_path
):
    repo = _local_checkout(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    selector = f"local-{commit[:12]}"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    with pytest.raises(ReleaseError, match="requires source_commit"):
        resolve_release(selector)
    with pytest.raises(ReleaseError, match="does not match source_commit"):
        resolve_release(
            "local-000000000000",
            source_commit=commit,
            source_checkout=repo,
        )
    with pytest.raises(ReleaseError, match="not a Git checkout"):
        resolve_release(
            selector,
            source_commit=commit,
            source_checkout=tmp_path / "missing",
        )
    with pytest.raises(ReleaseError, match="does not contain source_commit"):
        resolve_release(
            "local-000000000000",
            source_commit="0" * 40,
            source_checkout=repo,
        )

    cache = tmp_path / "xdg" / "manifest" / "releases" / f"local-{commit}"
    cache.parent.mkdir(parents=True)
    cache.write_text("invalid cache entry\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="cached local release is invalid"):
        resolve_release(selector, source_commit=commit, source_checkout=repo)
    assert cache.read_text(encoding="utf-8") == "invalid cache entry\n"


def test_receipt_pinned_local_release_removes_failed_submodule_materialization(
    monkeypatch, tmp_path
):
    repo = _local_checkout(tmp_path)
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    _git(dependency, "init")
    _git(dependency, "config", "user.email", "manifest@example.invalid")
    _git(dependency, "config", "user.name", "Manifest Test")
    (dependency / "inner.txt").write_text("submodule\n", encoding="utf-8")
    _git(dependency, "add", "inner.txt")
    _git(dependency, "commit", "-m", "dependency")
    dependency_commit = _git(dependency, "rev-parse", "HEAD")
    (repo / ".gitmodules").write_text(
        '[submodule "dependency"]\n'
        "\tpath = vendor/dependency\n"
        f"\turl = {tmp_path / 'missing-dependency'}\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".gitmodules")
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{dependency_commit},vendor/dependency",
    )
    _git(repo, "commit", "-m", "add unavailable dependency")
    commit = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    with pytest.raises(
        ReleaseError, match="initialize cached local release submodules"
    ):
        resolve_release(
            f"local-{commit[:12]}",
            source_commit=commit,
            source_checkout=repo,
        )

    cache = tmp_path / "xdg" / "manifest" / "releases" / f"local-{commit}"
    assert not cache.exists()


def test_bundle_checksum_ignores_untracked_python_runtime_files(tmp_path):
    repo = _local_checkout(tmp_path)
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore runtime bytecode")
    bundle = repo / "plugins"
    original = _tree_checksum(bundle)
    cache = bundle / "__pycache__"
    cache.mkdir()
    (cache / "bundle.cpython-313.pyc").write_bytes(b"runtime")

    assert _tree_checksum(bundle) == original
    (bundle / "bundle.txt").write_text("tracked change\n", encoding="utf-8")
    assert _tree_checksum(bundle) != original


def test_extracted_bundle_checksum_excludes_python_cache_paths(tmp_path):
    bundle = tmp_path / "extracted" / "plugins"
    bundle.mkdir(parents=True)
    (bundle / "bundle.txt").write_text("portable\n", encoding="utf-8")
    original = _tree_checksum(bundle)
    cache = bundle / "__pycache__"
    cache.mkdir()
    (cache / "bundle.pyc").write_bytes(b"runtime")
    (bundle / "bundle.pyc").write_bytes(b"runtime")

    assert _tree_checksum(bundle) == original
    (bundle / "bundle.txt").write_text("changed\n", encoding="utf-8")
    assert _tree_checksum(bundle) != original
