"""Focused immutable release-builder coverage using clean Git fixtures."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

import tools.build_manifest_release as release_builder
from manifest_agent.contracts import DOMAIN_BUNDLES
from tools.build_manifest_release import ReleaseBuildError, build_release

_BASE_URL = "https://downloads.example.invalid/manifest"


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(repo), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )


def _clean_fixture(repo_root: Path, tmp_path: Path) -> Path:
    fixture = tmp_path / "release-source"
    archive = subprocess.run(
        ("git", "-C", str(repo_root), "archive", "--format=tar", "HEAD"),
        check=True,
        capture_output=True,
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as source:
        for member in source.getmembers():
            target = fixture / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
                continue
            assert member.isfile()
            payload = source.extractfile(member)
            assert payload is not None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload.read())
    _git(fixture, "init")
    _git(fixture, "config", "user.email", "manifest@example.invalid")
    _git(fixture, "config", "user.name", "Manifest Test")
    _git(fixture, "add", ".")
    _git(fixture, "commit", "-m", "release fixture")
    return fixture


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)


def _bundle_digest(name: str, files: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    prefix = f"plugins/{name}/"
    for path in sorted(path for path in files if path.startswith(prefix)):
        record = files[path]
        relative = path.removeprefix(prefix).encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(int(str(record["mode"]), 8).to_bytes(2, "big"))
        digest.update(int(record["size"]).to_bytes(8, "big"))
        digest.update(bytes.fromhex(str(record["sha256"])))
    return digest.hexdigest()


def test_builds_exact_deterministic_eight_bundle_release(
    repo_root: Path, tmp_path: Path
) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    first = build_release(source, tmp_path / "first", _BASE_URL)
    second = build_release(source, tmp_path / "second", _BASE_URL)

    assert first.archive.name == "manifest-plugins-0.2.0.tar.gz"
    assert first.archive.read_bytes() == second.archive.read_bytes()
    assert first.metadata.read_bytes() == second.metadata.read_bytes()

    metadata = json.loads(first.metadata.read_text(encoding="utf-8"))
    assert set(metadata) == {
        "archive_sha256",
        "archive_url",
        "bundles",
        "commit",
        "files",
        "minimum_adapter_versions",
        "schema_version",
        "version",
    }
    assert metadata["version"] == "0.2.0"
    assert (
        metadata["commit"]
        == subprocess.run(
            ("git", "-C", str(source), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    assert metadata["archive_url"] == (
        "https://downloads.example.invalid/manifest/0.2.0/manifest-plugins-0.2.0.tar.gz"
    )
    assert (
        metadata["archive_sha256"]
        == hashlib.sha256(first.archive.read_bytes()).hexdigest()
    )
    assert metadata["minimum_adapter_versions"] == {
        "antigravity": "1",
        "claude": "1",
        "codex": "1",
        "cursor": "1",
        "devin": "1",
        "gemini": "1",
    }
    assert tuple(metadata["bundles"]) == DOMAIN_BUNDLES
    assert {name: set(bundle) for name, bundle in metadata["bundles"].items()} == {
        name: {"contract_schema_version", "sha256", "version"}
        for name in DOMAIN_BUNDLES
    }

    files = metadata["files"]
    assert all(set(record) == {"mode", "sha256", "size"} for record in files.values())
    assert ".claude-plugin/marketplace.json" in files
    assert all(
        path == ".claude-plugin/marketplace.json"
        or any(path.startswith(f"plugins/{name}/") for name in DOMAIN_BUNDLES)
        for path in files
    )
    assert not any(
        addon in path
        for addon in ("adversarial-design-loop", "manifest-docker")
        for path in files
    )
    for forbidden in ("bootstrap", "configs", ".apm", "templates", "src"):
        assert not any(
            path == forbidden or path.startswith(f"{forbidden}/") for path in files
        )
    for name in DOMAIN_BUNDLES:
        assert metadata["bundles"][name]["version"] == "0.2.0"
        assert metadata["bundles"][name]["contract_schema_version"] == 1
        assert metadata["bundles"][name]["sha256"] == _bundle_digest(name, files)

    prefix = "manifest-plugins-0.2.0/"
    marketplace_contents = b""
    with tarfile.open(first.archive, mode="r:gz") as bundle:
        members = bundle.getmembers()
        assert [member.name for member in members] == sorted(
            member.name for member in members
        )
        assert {member.name.removeprefix(prefix) for member in members} == set(files)
        for member in members:
            assert member.isfile()
            assert member.name.startswith(prefix)
            path = member.name.removeprefix(prefix)
            payload = bundle.extractfile(member)
            assert payload is not None
            contents = payload.read()
            record = files[path]
            assert len(contents) == record["size"]
            assert hashlib.sha256(contents).hexdigest() == record["sha256"]
            assert member.mode == int(record["mode"], 8)
            assert member.mtime == 0
            assert member.uid == member.gid == 0
            if path == ".claude-plugin/marketplace.json":
                marketplace_contents = contents

    marketplace = json.loads(marketplace_contents)
    assert tuple(plugin["name"] for plugin in marketplace["plugins"]) == DOMAIN_BUNDLES


def test_rejects_dirty_release_source(repo_root: Path, tmp_path: Path) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    (source / "README.md").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(ReleaseBuildError, match="must be clean"):
        build_release(source, tmp_path / "output", _BASE_URL)


def test_ignored_bundle_file_is_not_packaged(repo_root: Path, tmp_path: Path) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    ignored = source / "plugins/manifest-docs/ignored-release-secret.txt"
    exclude = source / ".git/info/exclude"
    exclude.write_text(
        exclude.read_text(encoding="utf-8")
        + "/plugins/manifest-docs/ignored-release-secret.txt\n",
        encoding="utf-8",
    )
    ignored.write_text("not a release artifact\n", encoding="utf-8")
    status = subprocess.run(
        ("git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"),
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""

    release = build_release(source, tmp_path / "output", _BASE_URL)
    metadata = json.loads(release.metadata.read_text(encoding="utf-8"))
    ignored_path = "plugins/manifest-docs/ignored-release-secret.txt"
    assert ignored_path not in metadata["files"]
    with tarfile.open(release.archive, mode="r:gz") as bundle:
        assert all(not member.name.endswith(ignored_path) for member in bundle)


def test_release_reads_immutable_head_blobs_after_inventory(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    relative = "plugins/manifest-docs/manifest-capabilities.yml"
    target = source / relative
    expected = subprocess.run(
        ("git", "-C", str(source), "show", f"HEAD:{relative}"),
        check=True,
        capture_output=True,
    ).stdout
    original = release_builder._tracked_bundle_files

    def mutate_after_inventory(root: Path, bundle_name: str):
        tracked = original(root, bundle_name)
        if bundle_name == "manifest-docs":
            target.write_text("tampered after inventory\n", encoding="utf-8")
        return tracked

    monkeypatch.setattr(
        release_builder, "_tracked_bundle_files", mutate_after_inventory
    )
    release = release_builder.build_release(source, tmp_path / "output", _BASE_URL)

    assert target.read_text(encoding="utf-8") == "tampered after inventory\n"
    metadata = json.loads(release.metadata.read_text(encoding="utf-8"))
    assert metadata["files"][relative]["sha256"] == hashlib.sha256(expected).hexdigest()
    with tarfile.open(release.archive, mode="r:gz") as bundle:
        member = bundle.getmember(f"manifest-plugins-0.2.0/{relative}")
        payload = bundle.extractfile(member)
        assert payload is not None
        assert payload.read() == expected


def test_rejects_invalid_domain_contract(repo_root: Path, tmp_path: Path) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    contract = source / "plugins/manifest-docs/manifest-capabilities.yml"
    contract.write_text(
        contract.read_text(encoding="utf-8").replace(
            "schema_version: 1", "schema_version: true", 1
        ),
        encoding="utf-8",
    )
    _commit(source, "invalidate domain contract")

    with pytest.raises(ReleaseBuildError, match="invalid domain contracts"):
        build_release(source, tmp_path / "output", _BASE_URL)


def test_rejects_mismatched_contract_versions(repo_root: Path, tmp_path: Path) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    bundle = source / "plugins/manifest-docs"
    contract = bundle / "manifest-capabilities.yml"
    contract.write_text(
        contract.read_text(encoding="utf-8").replace(
            "version: 0.2.0", "version: 0.3.0", 1
        ),
        encoding="utf-8",
    )
    for relative in (
        ".claude-plugin/plugin.json",
        "gemini-extension.json",
        "antigravity-extension.json",
        "plugin.json",
    ):
        path = bundle / relative
        document = json.loads(path.read_text(encoding="utf-8"))
        document["version"] = "0.3.0"
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    marketplace_path = source / ".claude-plugin/marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    next(entry for entry in marketplace["plugins"] if entry["name"] == "manifest-docs")[
        "version"
    ] = "0.3.0"
    marketplace_path.write_text(
        json.dumps(marketplace, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _commit(source, "mismatched domain version")

    with pytest.raises(ReleaseBuildError, match="versions must match"):
        build_release(source, tmp_path / "output", _BASE_URL)


def test_rejects_generated_view_drift(repo_root: Path, tmp_path: Path) -> None:
    source = _clean_fixture(repo_root, tmp_path)
    view = source / "plugins/manifest-docs/gemini-extension.json"
    view.write_text(view.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _commit(source, "drift generated view")

    with pytest.raises(ReleaseBuildError, match="generated views are not clean"):
        build_release(source, tmp_path / "output", _BASE_URL)


@pytest.mark.parametrize(
    "base_url",
    (
        "http://downloads.example.invalid/manifest",
        "https://user@example.invalid/manifest",
        "https://downloads.example.invalid/manifest?token=secret",
    ),
)
def test_rejects_unsafe_archive_base_url(
    repo_root: Path, tmp_path: Path, base_url: str
) -> None:
    source = _clean_fixture(repo_root, tmp_path)

    with pytest.raises(ReleaseBuildError, match="credential-free HTTPS"):
        build_release(source, tmp_path / "output", base_url)
