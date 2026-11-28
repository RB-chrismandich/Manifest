"""Observer staging replacement and cleanup ownership regressions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from manifest_agent.observer_runtime_identity import read_signed


@pytest.fixture
def authority(tmp_path):
    key = tmp_path / "ownership.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    return key


def test_observer_recovery_rejects_foreign_staging_parent(
    tmp_path, authority, monkeypatch
):
    from dataclasses import asdict

    import manifest_agent.observer_runtime as runtime
    from manifest_agent.observer_runtime_identity import (
        ObserverBinding,
        canonical,
        digest,
        generation_paths,
    )

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    binding = ObserverBinding(
        "a" * 40, "b" * 64, "c" * 64, "d" * 64, runtime.platform_id()
    )
    provider = {"path": str(Path(sys.executable).resolve())}
    root, _ = generation_paths(binding, provider, os.environ)
    root.parent.mkdir(parents=True)
    stage = root.parent / f".{root.name}.{os.getpid()}.staging"
    stage.mkdir()
    receipt = tmp_path / "selected.json"
    pending = {
        "receipt": str(receipt.absolute()),
        "binding": asdict(binding),
        "provider": provider,
        "stage": stage.name,
        "pid": os.getpid(),
        "inode": runtime._inode(stage),
        "owner": f"{binding.id}/{digest(canonical(provider))}",
        "store_lock_sha256": "e" * 64,
        "release_root": str(tmp_path / "release"),
    }
    runtime._write_signed(
        runtime._pending_path(receipt), pending, authority, runtime.PENDING_DOMAIN
    )
    stage.rename(stage.with_name(stage.name + ".original"))
    stage.mkdir()
    foreign = stage / "foreign"
    foreign.write_bytes(b"must survive")

    with pytest.raises(ValueError, match="observer pending stage was replaced"):
        runtime._recover(receipt, authority)

    assert foreign.read_bytes() == b"must survive"
    assert runtime._pending_path(receipt).exists()


def test_observer_stage_replacement_during_materialization_preserves_foreign_bytes(
    tmp_path, monkeypatch
):
    import manifest_agent.observer_runtime as runtime
    from manifest_agent.observer_runtime_identity import (
        ObserverBinding,
        generation_paths,
    )

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    release = tmp_path / "release"
    receipt = tmp_path / "selected.json"

    project = release / runtime.PROJECT
    project.mkdir(parents=True)
    (project / "uv-toolchain.lock.json").write_text("{}")
    runtime._observer_authority(receipt)
    binding = ObserverBinding(
        "a" * 40, "b" * 64, "c" * 64, "d" * 64, runtime.platform_id()
    )
    provider = {"path": str(Path(sys.executable).resolve())}
    root, record = generation_paths(binding, provider, os.environ)
    stage_path = root.parent / f".{root.name}.{os.getpid()}.staging"

    def replace_parent(*args, **kwargs):
        stage_path.rename(stage_path.with_name(stage_path.name + ".original"))
        stage_path.mkdir()
        (stage_path / "foreign").write_bytes(b"must survive")
        raise ValueError("injected materialization failure")

    monkeypatch.setattr(runtime, "_materialize_observer", replace_parent)
    desired = type("Desired", (), {"release_root": release})()
    with pytest.raises(ValueError, match="observer pending stage was replaced"):
        runtime._stage_observer(desired, binding, provider, receipt)
    assert (stage_path / "foreign").read_bytes() == b"must survive"
    assert stage_path.with_name(stage_path.name + ".original").is_dir()
    assert not root.exists()
    assert not record.exists()


@pytest.fixture
def observer_stage_case(tmp_path, monkeypatch):
    import manifest_agent.observer_runtime as runtime
    from manifest_agent.observer_runtime_identity import (
        ObserverBinding,
        generation_paths,
    )

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    release = tmp_path / "release"
    project = release / runtime.PROJECT
    project.mkdir(parents=True)
    (project / "uv-toolchain.lock.json").write_text("{}")
    receipt = tmp_path / "selected.json"
    key = runtime._observer_authority(receipt)
    binding = ObserverBinding(
        "a" * 40, "b" * 64, "c" * 64, "d" * 64, runtime.platform_id()
    )
    provider = {"path": str(Path(sys.executable).resolve())}
    root, record = generation_paths(binding, provider, os.environ)
    prior_binding = ObserverBinding(
        "e" * 40, "b" * 64, "c" * 64, "d" * 64, runtime.platform_id()
    )
    prior_root, prior_record = generation_paths(prior_binding, provider, os.environ)
    prior_root.mkdir(parents=True)
    (prior_root / "prior").write_bytes(b"prior generation")
    prior_record.parent.mkdir(parents=True, exist_ok=True)
    prior_record.write_bytes(b"prior record")
    desired = type(
        "Desired",
        (),
        {
            "release_root": release,
            "source": "https://example.invalid/archive",
            "all_contracts": (),
        },
    )()
    desired.bundle_path = lambda _: release / "plugins" / "manifest-workspace"
    monkeypatch.setattr(runtime, "_binding", lambda _: binding)
    monkeypatch.setattr(runtime, "_provider", lambda *_: provider)
    monkeypatch.setattr(runtime, "_source_unchanged", lambda _: None)
    stage = root.parent / f".{root.name}.{os.getpid()}.staging"
    return (
        runtime,
        desired,
        binding,
        receipt,
        key,
        stage,
        root,
        record,
        prior_root,
        prior_record,
    )


def test_observer_signing_swap_preserves_foreign_and_prior_generation(
    observer_stage_case, monkeypatch
):
    (
        runtime,
        desired,
        binding,
        receipt,
        key,
        stage,
        root,
        record,
        prior_root,
        prior_record,
    ) = observer_stage_case
    original_asdict = runtime.asdict
    original_inode = None

    def swap_before_signing(value):
        nonlocal original_inode
        if value is binding:
            original_inode = runtime._inode(stage)
            stage.rename(stage.with_name(stage.name + ".original"))
            stage.mkdir()
            (stage / "foreign").write_bytes(b"must survive")
        return original_asdict(value)

    def fail_materialization(*args, **kwargs):
        raise ValueError("injected materialization failure")

    monkeypatch.setattr(runtime, "asdict", swap_before_signing)
    monkeypatch.setattr(runtime, "_materialize_observer", fail_materialization)
    with pytest.raises(ValueError, match="observer pending stage was replaced"):
        runtime.prepare_observer_runtime(desired, receipt_path=receipt)

    pending = read_signed(
        runtime._pending_path(receipt), key, domain=runtime.PENDING_DOMAIN
    )
    assert pending["inode"] == original_inode
    assert pending["inode"] != runtime._inode(stage)
    assert (stage / "foreign").read_bytes() == b"must survive"
    assert stage.with_name(stage.name + ".original").is_dir()
    assert (prior_root / "prior").read_bytes() == b"prior generation"
    assert prior_record.read_bytes() == b"prior record"
    assert not root.exists()
    assert not record.exists()


@pytest.mark.parametrize("replacement", ["nonempty", "foreign-owned"])
def test_observer_refuses_unowned_stage_at_creation_without_deletion(
    observer_stage_case, monkeypatch, replacement
):
    from types import SimpleNamespace

    runtime, desired, _, receipt, _, stage, *_ = observer_stage_case
    original_mkdir = os.mkdir
    original_fstat = os.fstat
    foreign_inode = None

    def swap_at_mkdir(name, mode=0o777, *, dir_fd=None):
        nonlocal foreign_inode
        result = original_mkdir(name, mode, dir_fd=dir_fd)
        if name == stage.name and dir_fd is not None:
            stage.rename(stage.with_name(stage.name + ".original"))
            original_mkdir(stage.name, 0o777, dir_fd=dir_fd)
            foreign_inode = runtime._inode(stage)
            if replacement == "nonempty":
                (stage / "foreign").write_bytes(b"must survive")
        return result

    def foreign_owner(descriptor):
        info = original_fstat(descriptor)
        if (
            replacement == "foreign-owned"
            and [info.st_dev, info.st_ino] == foreign_inode
        ):
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_uid=os.geteuid() + 1,
                st_dev=info.st_dev,
                st_ino=info.st_ino,
            )
        return info

    monkeypatch.setattr(os, "mkdir", swap_at_mkdir)
    monkeypatch.setattr(os, "fstat", foreign_owner)
    with pytest.raises(ValueError, match="unowned observer stage"):
        runtime.prepare_observer_runtime(desired, receipt_path=receipt)

    _assert_unowned_stage_survives(observer_stage_case, foreign_inode, replacement)


def _assert_unowned_stage_survives(observer_stage_case, foreign_inode, replacement):
    runtime, _, _, receipt, _, stage, root, record, prior_root, prior_record = (
        observer_stage_case
    )
    assert stage.is_dir()
    assert runtime._inode(stage) == foreign_inode
    if replacement == "nonempty":
        assert (stage / "foreign").read_bytes() == b"must survive"
    assert stage.with_name(stage.name + ".original").is_dir()
    assert not runtime._pending_path(receipt).exists()
    assert (prior_root / "prior").read_bytes() == b"prior generation"
    assert prior_record.read_bytes() == b"prior record"
    assert not root.exists()
    assert not record.exists()


# Stage removal is non-recursive after an emptiness check; late contents survive.
def test_observer_stage_swap_after_emptiness_check_preserves_sentinel(
    observer_stage_case, monkeypatch
):
    runtime, desired, _, receipt, _, stage, *_ = observer_stage_case
    original_mkdir = os.mkdir
    original_listdir = os.listdir
    swapped = False
    empty_checked = False
    sentinel_written = False
    materialization_failed = False

    def swap_before_stage_open(name, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        result = original_mkdir(name, mode, dir_fd=dir_fd)
        if name == stage.name and dir_fd is not None and not swapped:
            stage.rename(stage.with_name(stage.name + ".original"))
            original_mkdir(name, mode, dir_fd=dir_fd)
            swapped = True
        return result

    def add_sentinel_after_check(descriptor):
        nonlocal empty_checked, sentinel_written
        entries = original_listdir(descriptor)
        if swapped and not empty_checked and not entries:
            empty_checked = True
            (stage / "sentinel").write_bytes(b"must survive")
            sentinel_written = True
        return entries

    def fail_materialization(*args, **kwargs):
        nonlocal materialization_failed
        materialization_failed = True
        raise ValueError("injected materialization failure")

    monkeypatch.setattr(os, "mkdir", swap_before_stage_open)
    monkeypatch.setattr(os, "listdir", add_sentinel_after_check)
    monkeypatch.setattr(runtime, "_materialize_observer", fail_materialization)
    with pytest.raises(ValueError, match="injected materialization failure"):
        runtime.prepare_observer_runtime(desired, receipt_path=receipt)
    try:
        assert swapped, "mkdir-to-open swap was not reached"
        assert empty_checked, "replacement emptiness check was not reached"
        assert sentinel_written, "sentinel was not written"
        assert materialization_failed, (
            "injected materialization failure was not reached"
        )
    except AssertionError as error:
        raise RuntimeError("race fixture did not reach every checkpoint") from error
    sentinel = stage / "sentinel"
    assert sentinel.exists() and sentinel.read_bytes() == b"must survive"


def test_incomplete_stage_survives_recovery_without_blocking_later_attempt(
    observer_stage_case, monkeypatch
):
    runtime, desired, _, receipt, key, stage, *_ = observer_stage_case
    attempts = []

    def fail_materialization(desired, environment, *args):
        attempts.append(environment.parent)
        (environment.parent / "sentinel").write_bytes(b"must survive")
        raise ValueError("injected incomplete materialization")

    monkeypatch.setattr(runtime, "_materialize_observer", fail_materialization)
    for _ in range(2):
        with (
            pytest.warns(RuntimeWarning, match="incomplete stage preserved"),
            pytest.raises(ValueError, match="injected incomplete materialization"),
        ):
            runtime.prepare_observer_runtime(desired, receipt_path=receipt)
        runtime._recover(receipt, key)
        assert not runtime._pending_path(receipt).exists()
        assert (stage / "sentinel").read_bytes() == b"must survive"
    assert len(attempts) == 2 and attempts[0] != attempts[1]
    state = runtime.runtime_roots(os.environ)[1]
    evidence = tuple((state / "retained").glob("*.json"))
    assert len(evidence) == 2
    for path in evidence:
        document = read_signed(path, key, domain=runtime.PENDING_DOMAIN + "-retained")
        assert document["status"] == "retained-unresolved"
        assert document["pending"]["stage"] in {attempt.name for attempt in attempts}
