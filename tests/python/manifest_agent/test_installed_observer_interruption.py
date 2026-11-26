"""Observer installation interruption and recovery scenarios."""

from tests.python.manifest_agent._installed_observer_fixtures import (
    HARNESSES,
    ROOT,
    Path,
    bundle_checksums,
    digest,
    generation_paths,
    inventory,
    isolated_transaction,
    json,
    observer_key_path,
    os,
    pytest,
    replace,
    runtime,
    runtime_roots,
    select,
    subprocess,
    sys,
    tarfile,
    with_source_fingerprints,
    write_receipt_atomic,
)


def test_actual_uv_provision_interruption_recovers_dedicated_store(
    installed_observer, tmp_path, monkeypatch
):
    import shutil

    fixture = installed_observer
    env, receipt = isolated_transaction(
        fixture, tmp_path / "uv-interruption", monkeypatch
    )
    source = tmp_path / "release"
    shutil.copytree(fixture["desired"].release_root, source)
    projection = source / runtime.PROJECT / "uv-toolchain.lock.json"
    projection.write_bytes(projection.read_bytes() + b"\n\n")
    desired = with_source_fingerprints(
        replace(
            fixture["desired"],
            release_root=source,
            archive_sha256=digest(b"uv-interruption"),
        )
    )
    gate = tmp_path / "developer-gate-store"
    gate.mkdir()
    (gate / "manifest.json").write_text(
        "developer gate inventory must remain byte-identical"
    )
    env = {
        **env,
        "MANIFEST_TOOLCHAIN_STORE": str(gate),
        "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT))),
    }
    before = inventory(gate)
    code = _uv_interruption_program()
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(receipt),
            str(source),
            str(fixture["uv_archive"]),
            desired.archive_sha256,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 73, process.stderr
    _assert_uv_interruption_recovered(
        fixture, receipt, env, gate, before, source, projection
    )


def _uv_interruption_program():
    return """
import json, os, sys
from dataclasses import replace
from pathlib import Path
import manifest_agent.observer_runtime as runtime
from manifest_agent.checks import toolchain_provision as provisioner
from manifest_agent.native_observation import _desired_state
from manifest_agent.state import read_receipt, installation_lock
receipt, source, archive = map(Path, sys.argv[1:4])
desired = replace(_desired_state(source, read_receipt(receipt), published=True),
                  archive_sha256=sys.argv[4])
tool = json.loads((source / runtime.PROJECT / "uv-toolchain.lock.json").read_bytes())["tools"]["uv"]
pin = tool["platforms"][runtime.platform_id()]
def fetch(url):
    assert url == pin["url"]
    payload = archive.read_bytes()
    assert runtime.digest(payload) == pin["sha256"]
    return payload
from tests.python.manifest_agent._observer_locked_cache import offline_materializer_run
from manifest_agent.checks import toolchain_materialize as materializer
materializer._run = offline_materializer_run(materializer._run)
write = provisioner.write_file
def interrupted(store, relative, content, mode):
    write(store, relative, content, mode)
    if relative == f"tools/uv/{tool['version']}/bin/uv":
        os._exit(73)
provisioner.write_file = interrupted
runtime.provision = lambda *a, **kw: provisioner.provision(*a, **kw, fetcher=fetch)
with installation_lock(receipt.parent / "install.lock"):
    runtime.prepare_observer_runtime(desired, receipt_path=receipt)
"""


def _assert_uv_interruption_recovered(
    fixture, receipt, env, gate, before, source, projection
):
    from manifest_agent.checks import toolchain

    store = (
        runtime_roots(env)[0]
        / "toolchains"
        / digest(projection.read_bytes())
        / runtime.platform_id()
    )
    assert store == runtime._store_path(source / runtime.PROJECT, runtime.platform_id())
    assert store.is_dir()
    marker = runtime._store_owner(store, observer_key_path(env))
    assert marker["phase"] == "materializing"
    lock = json.loads(projection.read_bytes())
    resolved = toolchain.resolve(
        "store:uv/bin/uv",
        lock=lock,
        store=store,
        platform=runtime.platform_id(),
        repo_root=source,
    )
    assert isinstance(resolved, toolchain.BlockedReason)
    runtime._recover(receipt, observer_key_path(env))
    assert not store.exists()
    assert inventory(gate) == before
    assert fixture["record"].exists() and fixture["environment"].exists()


def test_last_owner_removes_only_exact_dedicated_store(
    installed_observer, tmp_path, monkeypatch
):
    import shutil

    fixture = installed_observer
    source = tmp_path / "release"
    shutil.copytree(fixture["desired"].release_root, source)
    projection = source / runtime.PROJECT / "uv-toolchain.lock.json"
    projection.write_bytes(projection.read_bytes() + b"\n\n\n")
    desired = with_source_fingerprints(
        replace(
            fixture["desired"],
            release_root=source,
            archive_sha256=digest(b"dedicated-last-owner"),
        )
    )
    gate = tmp_path / "gate-store"
    gate.mkdir()
    (gate / "manifest.json").write_bytes(b"unchanged developer cache")
    before = inventory(gate)
    monkeypatch.setenv("MANIFEST_TOOLCHAIN_STORE", str(gate))
    first, second = tmp_path / "first/receipt.json", tmp_path / "second/receipt.json"
    original = select(fixture, "claude")
    selected = replace(
        original,
        archive_sha256=desired.archive_sha256,
        bundle_checksums=bundle_checksums(desired),
    )
    runtime.prepare_observer_runtime(desired, receipt_path=first)
    write_receipt_atomic(first, selected)
    runtime.prepare_observer_runtime(desired, receipt_path=second)
    write_receipt_atomic(second, selected)
    store = (
        runtime_roots(fixture["env"])[0]
        / "toolchains"
        / digest(projection.read_bytes())
        / runtime.platform_id()
    )
    assert store == runtime._store_path(source / runtime.PROJECT, runtime.platform_id())
    runtime.queue_observer_cleanup(first)
    first.unlink()
    runtime.remove_observer(first)
    assert store.is_dir(), "second receipt retains shared store"
    assert inventory(gate) == before
    runtime.queue_observer_cleanup(second)
    second.unlink()
    runtime.remove_observer(second)
    assert not store.exists()
    assert inventory(gate) == before


def test_archived_wheel_and_sdist_include_every_observer_input(
    installed_observer, tmp_path
):
    import tomllib

    fixture = installed_observer
    project = fixture["desired"].release_root / runtime.PROJECT
    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    code = (
        "import hatchling.build, os, sys; os.chdir(sys.argv[1]); "
        "print(hatchling.build.build_wheel(sys.argv[2])); "
        "print(hatchling.build.build_sdist(sys.argv[2]))"
    )
    result = subprocess.run(
        [
            str(fixture["environment"] / "bin/python"),
            "-I",
            "-B",
            "-c",
            code,
            str(project),
            str(tmp_path),
        ],
        env={**fixture["env"], "UV_OFFLINE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    _assert_archived_package_inputs(project, metadata, tmp_path)


def _assert_archived_package_inputs(project, metadata, tmp_path):
    import zipfile

    wheel = next(tmp_path.glob("*.whl"))
    sdist = next(tmp_path.glob("*.tar.gz"))
    with zipfile.ZipFile(wheel) as archive:
        for source, destination in metadata["tool"]["hatch"]["build"]["targets"][
            "wheel"
        ]["force-include"].items():
            assert archive.read(destination) == (project / source).read_bytes()
        assert (
            archive.read("manifest_agent/observer_runtime.py")
            == (project / "src/manifest_agent/observer_runtime.py").read_bytes()
        )
    with tarfile.open(sdist) as archive:
        members = {
            "/".join(member.name.split("/")[1:]): member
            for member in archive.getmembers()
        }
        expected = {
            "pyproject.toml",
            "uv.lock",
            "uv-toolchain.lock.json",
            "observe.py",
            "observer_runtime_identity.py",
        }
        expected.update(
            metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        )
        expected.update(
            str(path.relative_to(project))
            for path in (project / "src").rglob("*")
            if path.is_file()
        )
        assert expected <= set(members)
        for name in expected:
            assert (
                archive.extractfile(members[name]).read()
                == (project / name).read_bytes()
            )


@pytest.mark.parametrize(
    "interruption", ["regular-file", "intermediate-interpreter-link"]
)
def test_partial_generation_retirement_is_signed_resumable_and_refuses_changes(
    installed_observer, tmp_path, monkeypatch, interruption
):
    from manifest_agent.service_state import persist_remaining

    fixture = installed_observer
    desired = replace(
        fixture["desired"],
        archive_sha256=digest(f"partial-retirement-{interruption}".encode()),
    )
    receipt_path = tmp_path / "owner/receipt.json"
    binding = runtime.prepare_observer_runtime(desired, receipt_path=receipt_path)
    provider = runtime._provider(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    root, record = generation_paths(binding, provider, fixture["env"])
    selected = replace(select(fixture, "claude"), archive_sha256=desired.archive_sha256)
    write_receipt_atomic(receipt_path, selected)
    original = inventory(fixture["environment"])
    with pytest.raises(ValueError, match="receipt still selects"):
        runtime.remove_observer(receipt_path)
    assert root.exists() and record.exists()
    runtime.queue_observer_cleanup(receipt_path)
    persist_remaining(receipt_path, selected, {}, HARNESSES)
    _exercise_partial_generation_retirement(
        runtime,
        root,
        record,
        receipt_path,
        provider,
        fixture,
        original,
        interruption,
        monkeypatch,
    )


def _exercise_partial_generation_retirement(
    runtime,
    root,
    record,
    receipt_path,
    provider,
    fixture,
    original,
    interruption,
    monkeypatch,
):
    files = sorted(
        path for path in root.rglob("*.py") if path.is_file() and not path.is_symlink()
    )
    assert len(files) > 1
    removed, surviving = files[:2]
    removed, surviving_alias, alias_target = _partial_removal_target(
        root, removed, surviving, interruption
    )
    payload = surviving.read_bytes()
    remove = runtime._remove_tree_at

    def interrupted(parent, name, *, expected_inode=None, files):
        removed.unlink()
        raise OSError("interrupted generation deletion")

    monkeypatch.setattr(runtime, "_remove_tree_at", interrupted)
    with pytest.raises(OSError, match="interrupted generation"):
        runtime.remove_observer(receipt_path)
    assert record.exists() and not removed.exists()
    if surviving_alias is not None:
        assert surviving_alias.is_symlink() and not surviving_alias.exists()
        # Live runtime validation remains strict even though cleanup can resume.
        with pytest.raises(FileNotFoundError):
            runtime.environment_inventory(root, provider)
    monkeypatch.setattr(runtime, "_remove_tree_at", remove)
    surviving.write_bytes(b"changed surviving bytes")
    with pytest.raises(ValueError, match="surviving files changed"):
        runtime.remove_observer(receipt_path)
    assert surviving.read_bytes() == b"changed surviving bytes"
    surviving.write_bytes(payload)
    original_mode = surviving.stat().st_mode & 0o7777
    surviving.chmod(original_mode ^ 0o100)
    with pytest.raises(ValueError, match="surviving files changed"):
        runtime.remove_observer(receipt_path)
    surviving.chmod(original_mode)
    if surviving_alias is not None:
        surviving_alias.unlink()
        surviving_alias.symlink_to("modified-interpreter-target")
        with pytest.raises(ValueError, match="surviving files changed"):
            runtime.remove_observer(receipt_path)
        assert surviving_alias.readlink() == Path("modified-interpreter-target")
        surviving_alias.unlink()
        surviving_alias.symlink_to(alias_target)
    runtime.remove_observer(receipt_path)
    _assert_original_environment(fixture, original, root, record)


def _partial_removal_target(root, removed, surviving, interruption):
    surviving_alias = None
    alias_target = None
    if interruption == "intermediate-interpreter-link":
        aliases = [
            path
            for path in (root / "bin").glob("python*")
            if path.is_symlink()
            and not path.readlink().is_absolute()
            and (path.parent / path.readlink()).is_symlink()
        ]
        assert aliases, "real UV environment must supply an internal interpreter alias"
        surviving_alias = aliases[0]
        alias_target = surviving_alias.readlink()
        removed = surviving_alias.parent / alias_target
        assert removed != surviving_alias
    return removed, surviving_alias, alias_target


def _assert_original_environment(fixture, original, root, record):
    assert not root.exists() and not record.exists()
    assert inventory(fixture["environment"]) == original


def test_ambiguous_receipt_publication_preserves_all_generations(
    installed_observer, tmp_path, monkeypatch
):
    fixture = installed_observer
    desired = replace(
        fixture["desired"], archive_sha256=digest(b"ambiguous-publication")
    )
    receipt_path = tmp_path / "owner/receipt.json"
    old = select(fixture, "claude")
    write_receipt_atomic(receipt_path, old)
    before = inventory(fixture["environment"])
    target = replace(old, archive_sha256=desired.archive_sha256)

    def ambiguous(path, receipt):
        write_receipt_atomic(path, receipt)
        raise OSError("publication acknowledgement lost")

    def unreadable(path):
        raise OSError("receipt read temporarily unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(runtime, "write_receipt_atomic", ambiguous)
        patch.setattr(runtime, "read_receipt", unreadable)
        with (
            pytest.raises(RuntimeError, match="publication is unreadable"),
            runtime.ObserverTransaction(desired, receipt_path) as transaction,
        ):
            transaction.persist(target)
    root, record = generation_paths(
        transaction.binding, transaction.provider, fixture["env"]
    )
    assert root.exists() and record.exists()
    assert inventory(fixture["environment"]) == before
    runtime.queue_observer_cleanup(receipt_path)
    receipt_path.unlink()
    runtime.remove_observer(receipt_path)
    assert fixture["record"].exists() and fixture["environment"].exists()


def test_generation_retirement_preserves_unknown_entries_at_deletion(
    installed_observer, tmp_path, monkeypatch
):
    from manifest_agent.service_state import persist_remaining

    fixture = installed_observer
    desired = replace(
        fixture["desired"], archive_sha256=digest(b"late-unknown-retirement")
    )
    receipt = tmp_path / "owner/receipt.json"
    binding = runtime.prepare_observer_runtime(desired, receipt_path=receipt)
    provider = runtime._provider(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    root, record = generation_paths(binding, provider, fixture["env"])
    selected = replace(select(fixture, "claude"), archive_sha256=desired.archive_sha256)
    write_receipt_atomic(receipt, selected)
    runtime.queue_observer_cleanup(receipt)
    persist_remaining(receipt, selected, {}, HARNESSES)
    remove = runtime._remove_tree_at

    def late_contents(parent, name, *, expected_inode, files):
        (root / "unknown").mkdir()
        (root / "unknown/sentinel").write_bytes(b"must survive")
        return remove(parent, name, expected_inode=expected_inode, files=files)

    monkeypatch.setattr(runtime, "_remove_tree_at", late_contents)
    with pytest.raises(ValueError, match="unowned contents"):
        runtime.remove_observer(receipt)
    assert (root / "unknown/sentinel").read_bytes() == b"must survive"
    assert record.exists()
    state = runtime_roots(fixture["env"])[1]
    assert tuple((state / "retirements").glob("*.json"))
    monkeypatch.setattr(runtime, "_remove_tree_at", remove)
    with pytest.raises(ValueError, match="surviving files changed"):
        runtime.remove_observer(receipt)
    assert (root / "unknown/sentinel").read_bytes() == b"must survive"
