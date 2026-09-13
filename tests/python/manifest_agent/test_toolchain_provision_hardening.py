from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

from manifest_agent.checks import toolchain
from manifest_agent.checks import toolchain_provision as provision


def _archive(name: str, contents: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(contents)
        archive.addfile(member, io.BytesIO(contents))
    return buffer.getvalue()


def _lock(data: bytes, *, version: str | None = "1.0.0") -> dict:
    executable = b"verified binary"
    return {
        "schema_version": 1,
        "tools": {
            "demo": {
                "kind": "binary",
                "version": version,
                "platforms": {
                    "linux-x64": {
                        "url": "https://example.invalid/demo.tgz",
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "exe_sha256": hashlib.sha256(executable).hexdigest(),
                        "path_in_archive": "demo",
                    }
                },
            }
        },
    }


def test_missing_tool_version_is_explicitly_unpinned(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive, version=None)

    outcome = provision.provision(
        lock, tmp_path / "store", platform="linux-x64", fetcher=lambda _: archive
    )

    assert outcome[0].status == "blocked"
    assert "UNPINNED" in outcome[0].reason


def test_offline_rejects_unattested_locked_artifact(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    lock["tools"]["demo"]["platforms"]["linux-x64"]["exe_sha256"] = None

    complete, problems = provision.validate_offline(
        lock, tmp_path / "store", "linux-x64"
    )

    assert not complete
    assert any("unattested" in problem for problem in problems)


def test_store_root_rejects_symlink_escape_into_checkout(tmp_path: Path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "store").symlink_to(checkout, target_is_directory=True)
    monkeypatch.chdir(checkout)

    try:
        toolchain.store_root({"MANIFEST_TOOLCHAIN_STORE": str(outside / "store")})
    except toolchain.UnsafeStoreLocationError:
        return
    raise AssertionError("symlinked store escape was accepted")


def test_resolve_rejects_manifest_symlink_escape(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    store = tmp_path / "store"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "demo"
    target.write_bytes(b"verified binary")
    link = store / "tools" / "demo" / "1.0.0" / "bin" / "demo"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    manifest = (
        f'{{"lock_digest":"{toolchain.lock_digest(lock)}","platform":"linux-x64",'
        f'"tools":{{"demo":{{"platform":"linux-x64","version":"1.0.0",'
        f'"source":"https://example.invalid/demo.tgz","source_sha256":"'
        f'{lock["tools"]["demo"]["platforms"]["linux-x64"]["sha256"]}",'
        '"executables":{"bin/demo":{"path":"tools/demo/1.0.0/bin/demo"}}}}}'
    )
    (store / "manifest.json").write_text(manifest)

    result = toolchain.resolve(
        "store:demo/bin/demo", lock=lock, store=store, platform="linux-x64"
    )

    assert result == toolchain.BlockedReason(
        "toolchain: demo not provisioned (run manifest provision)"
    )


def test_lock_parser_rejects_unsafe_archive_member(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    lock["tools"]["demo"]["platforms"]["linux-x64"]["path_in_archive"] = "../demo"

    try:
        provision.provision(
            lock, tmp_path / "store", platform="linux-x64", fetcher=lambda _: archive
        )
    except ValueError as error:
        assert "unsafe archive path" in str(error)
        return
    raise AssertionError("unsafe archive member was accepted")


def test_env_source_cannot_escape_checkout(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    lock["tools"]["demo"]["kind"] = "python-env"
    lock["tools"]["demo"]["platforms"]["linux-x64"]["url"] = "file://../outside"
    outside = tmp_path / "outside"
    outside.write_bytes(archive)

    outcome = provision.provision(
        lock,
        tmp_path / "store",
        platform="linux-x64",
        repo_root=tmp_path / "checkout",
    )

    assert outcome[0].status == "blocked"
    assert "unsafe path" in outcome[0].reason


def test_attestation_binds_lock_platform_tool_version_and_source(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    store = tmp_path / "store"

    provision.provision(lock, store, platform="linux-x64", fetcher=lambda _: archive)

    manifest = __import__("json").loads((store / "manifest.json").read_text())
    attestation = manifest["tools"]["demo"]
    assert manifest["lock_digest"] == toolchain.lock_digest(lock)
    assert manifest["platform"] == "linux-x64"
    assert attestation["platform"] == "linux-x64"
    assert attestation["version"] == "1.0.0"
    assert attestation["source"] == "https://example.invalid/demo.tgz"
    assert (
        attestation["executables"]["bin/demo"]["sha256"]
        == lock["tools"]["demo"]["platforms"]["linux-x64"]["exe_sha256"]
    )


def test_lock_validation_rejects_path_components_and_untrusted_urls():
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    lock["tools"]["demo"]["version"] = "../outside"

    try:
        provision.validate_lock(lock)
    except ValueError as error:
        assert "version" in str(error)
    else:
        raise AssertionError("unsafe version was accepted")

    lock = _lock(archive)
    lock["tools"]["demo"]["platforms"]["linux-x64"]["url"] = "http://127.0.0.1/"
    try:
        provision.validate_lock(lock)
    except ValueError as error:
        assert "URL" in str(error)
    else:
        raise AssertionError("loopback URL was accepted")


def test_provision_rejects_primary_payload_mismatch_before_recording(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    lock["tools"]["demo"]["platforms"]["linux-x64"]["exe_sha256"] = "0" * 64

    outcome = provision.provision(
        lock, tmp_path / "store", platform="linux-x64", fetcher=lambda _: archive
    )

    assert outcome[0].status == "blocked"
    assert "digest mismatch" in outcome[0].reason
    assert not (tmp_path / "store" / "manifest.json").exists()


def test_provision_refuses_a_store_destination_symlink(tmp_path: Path):
    archive = _archive("demo", b"verified binary")
    lock = _lock(archive)
    store = tmp_path / "store"
    target = store / "tools" / "demo" / "1.0.0" / "bin" / "demo"
    target.parent.mkdir(parents=True)
    target.symlink_to(tmp_path / "outside")

    outcome = provision.provision(
        lock, store, platform="linux-x64", fetcher=lambda _: archive
    )

    assert outcome[0].status == "blocked"
    assert not (tmp_path / "outside").exists()
