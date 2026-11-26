import json

from tests.python.manifest_agent._installed_observer_fixtures import (
    HARNESSES,
    ROOT,
    Path,
    canonical,
    digest,
    generation_paths,
    installation_lock,
    inventory,
    isolated_public_command,
    isolated_transaction,
    observer_key_path,
    os,
    pytest,
    replace,
    runtime,
    runtime_roots,
    select,
    subprocess,
    sys,
    write_receipt_atomic,
)


@pytest.mark.parametrize("harness", HARNESSES)
def test_public_installed_launch_preserves_explicit_receipt_and_absence_evidence(
    installed_observer, tmp_path, harness
):
    fixture = installed_observer
    select(fixture, harness)
    default = Path(fixture["env"]["XDG_STATE_HOME"]) / "manifest/installation.json"
    default.parent.mkdir(parents=True, exist_ok=True)
    default.write_text("invalid default receipt must never be read")
    poison = tmp_path / "manifest_agent"
    poison.mkdir()
    (poison / "__init__.py").write_text(
        'raise RuntimeError("source import escaped isolation")\n'
    )
    launcher = (
        fixture["desired"].bundle_path("manifest-workspace")
        / "runtime/observer/observe.py"
    )
    env = {
        **fixture["env"],
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(tmp_path),
        "MANIFEST_TOOLCHAIN_STORE": str(tmp_path / "forbidden-gate-store"),
    }
    roots = [
        fixture["environment"],
        *runtime_roots(env),
        Path(env["XDG_CACHE_HOME"]),
        fixture["receipt"].parent,
    ]
    before = [inventory(root) for root in roots]
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            str(launcher),
            "--json",
            "--receipt",
            str(fixture["receipt"]),
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["errors"] == []
    assert set(report["harnesses"]) == {harness}
    assert report["harnesses"][harness]["state"] == "BLOCKED"
    assert report["harnesses"][harness]["verified"] is False
    assert [inventory(root) for root in roots] == before
    assert not (tmp_path / "forbidden-gate-store").exists()
    assert not (poison / "__pycache__").exists()


@pytest.mark.parametrize(
    "entrypoint",
    ["env-check/scripts/env_check.py", "deploy-reconcile/scripts/plugin_reconcile.py"],
)
def test_public_bundle_entrypoints_forward_explicit_receipt(
    installed_observer, tmp_path, entrypoint
):
    fixture = installed_observer
    select(fixture, "claude")
    bundle = fixture["desired"].bundle_path("manifest-workspace")
    public_env = {**fixture["env"], "PATH": "/usr/bin:/bin"}
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONDONTWRITEBYTECODE"):
        public_env.pop(name, None)
    result = subprocess.run(
        [
            sys.executable,
            str(bundle / "skills" / entrypoint),
            "--json",
            "--receipt",
            str(fixture["receipt"]),
        ],
        env=public_env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout, result.stderr
    report = json.loads(result.stdout)
    assert report["native_observed"] is True
    assert set(report["harnesses"]) == {"claude"}
    assert "invalid default" not in result.stdout


@pytest.mark.parametrize("failure", ["startup", "post-materialization"])
def test_failed_new_generation_cleans_owned_store_marker(
    installed_observer, monkeypatch, failure
):
    fixture = installed_observer
    desired = replace(fixture["desired"], archive_sha256=digest(failure.encode()))
    binding = runtime._binding(desired)
    provider = runtime._provider(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    root, record = generation_paths(binding, provider, fixture["env"])
    prior = inventory(fixture["environment"])
    if failure == "startup":

        def rejected(*args):
            raise ValueError("injected installed startup rejection")

        monkeypatch.setattr(runtime, "_smoke", rejected)
    else:
        original = runtime._source_unchanged
        calls = []

        def rejected(value):
            original(value)
            calls.append(value)
            if len(calls) == 2:
                raise ValueError("injected post-materialization fingerprint rejection")

        monkeypatch.setattr(runtime, "_source_unchanged", rejected)
    with (
        installation_lock(fixture["receipt"].parent / "install.lock"),
        pytest.raises(ValueError, match="injected"),
    ):
        runtime.prepare_observer_runtime(desired, receipt_path=fixture["receipt"])
    assert not root.exists()
    assert not record.exists()
    assert not runtime._pending_path(fixture["receipt"]).exists()
    store = runtime._store_path(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    marker = runtime._store_owner(store, observer_key_path(fixture["env"]))
    assert f"{binding.id}/{digest(canonical(provider))}" not in marker["owners"]
    assert marker["phase"] == "ready"
    assert inventory(fixture["environment"]) == prior


def test_real_materialization_hard_exit_recovers_only_interrupted_generation(
    installed_observer, tmp_path, monkeypatch
):
    fixture = installed_observer
    env, receipt = isolated_transaction(fixture, tmp_path / "hard-exit", monkeypatch)
    desired = replace(
        fixture["desired"], archive_sha256=digest(b"interrupted-generation")
    )
    binding = runtime._binding(desired)
    provider = runtime._provider(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    root, record = generation_paths(binding, provider, env)
    prior = inventory(fixture["environment"])
    code = _hard_exit_generation_code()
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(receipt),
            str(desired.release_root),
            str(fixture["uv_archive"]),
            desired.archive_sha256,
        ],
        env={**env, "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT)))},
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 73, process.stderr
    assert runtime._pending_path(receipt).exists()
    with installation_lock(receipt.parent / "install.lock"):
        recovered = runtime.prepare_observer_runtime(
            fixture["desired"], receipt_path=receipt
        )
    assert recovered == fixture["binding"]
    assert not root.exists()
    assert not record.exists()
    assert not runtime._pending_path(receipt).exists()
    assert not list(root.parent.glob(f".{root.name}.*.staging"))
    store = runtime._store_path(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    marker = runtime._store_owner(store, observer_key_path(env))
    assert f"{binding.id}/{digest(canonical(provider))}" not in marker["owners"]
    assert marker["phase"] == "ready"
    assert inventory(fixture["environment"]) == prior


def _hard_exit_generation_code():
    code = """
import json, os, sys
from dataclasses import replace
from pathlib import Path
import manifest_agent.observer_runtime as runtime
from manifest_agent.native_observation import _desired_state
from manifest_agent.checks.toolchain_provision import provision
from manifest_agent.state import read_receipt, installation_lock
receipt_path, source, archive, expected = map(Path, sys.argv[1:5])
receipt = read_receipt(receipt_path)
desired = replace(_desired_state(source, receipt, published=True), archive_sha256=expected.name)
pin = json.loads((source / runtime.PROJECT / "uv-toolchain.lock.json").read_bytes())["tools"]["uv"]["platforms"][runtime.platform_id()]
def fetch(url):
    assert url == pin["url"]
    data = archive.read_bytes()
    assert runtime.digest(data) == pin["sha256"]
    return data
runtime.provision = lambda *a, **kw: provision(*a, **kw, fetcher=fetch)
from tests.python.manifest_agent._observer_locked_cache import offline_materializer_run
from manifest_agent.checks import toolchain_materialize as materializer
materializer._run = offline_materializer_run(materializer._run)
runtime._smoke = lambda *a: os._exit(73)
with installation_lock(receipt_path.parent / "install.lock"):
    runtime.prepare_observer_runtime(desired, receipt_path=receipt_path)
"""
    return code


def test_missing_source_fingerprint_is_nonsuccess_before_any_mutation(
    installed_observer,
):
    fixture = installed_observer
    desired = replace(fixture["desired"], source_workspace_sha256=None)
    roots = [*runtime_roots(fixture["env"]), fixture["receipt"].parent]
    before = [inventory(root) for root in roots]
    with pytest.raises(ValueError, match="source fingerprint is missing"):
        runtime.prepare_observer_runtime(desired, receipt_path=fixture["receipt"])
    assert [inventory(root) for root in roots] == before


def test_last_receipt_owner_retires_only_its_generation(installed_observer):
    fixture = installed_observer
    desired = replace(fixture["desired"], archive_sha256=digest(b"last-owner"))
    first = fixture["receipt"].with_name("first-owner.json")
    second = fixture["base"] / "separate-receipt-parent/second-owner.json"
    original = select(fixture, "claude")
    selected = replace(original, archive_sha256=desired.archive_sha256)
    with installation_lock(first.parent / "install.lock"):
        binding = runtime.prepare_observer_runtime(desired, receipt_path=first)
        write_receipt_atomic(first, selected)
        assert runtime.prepare_observer_runtime(desired, receipt_path=second) == binding
        write_receipt_atomic(second, selected)
        provider = runtime._provider(
            desired.release_root / runtime.PROJECT, binding.platform
        )
        root, record = generation_paths(binding, provider, fixture["env"])
        runtime.queue_observer_cleanup(first)
        first.unlink()
        runtime.remove_observer(first)
        assert root.exists() and record.exists()
        runtime.queue_observer_cleanup(second)
        second.unlink()
        runtime.remove_observer(second)
        assert not root.exists() and not record.exists()
    assert fixture["environment"].exists()
    assert fixture["record"].exists()


@pytest.mark.parametrize(
    "entrypoint",
    ("env-check/scripts/env_check.py", "deploy-reconcile/scripts/plugin_reconcile.py"),
)
@pytest.mark.parametrize(
    "failure",
    (
        "missing",
        "stale",
        "tampered",
        "runtime-file",
        "record-proof",
        "provider",
        "wrong-binding",
        "contracts",
    ),
)
def test_public_installed_failures_are_explicit_and_read_only(
    installed_observer, tmp_path, entrypoint, failure
):
    import shutil

    fixture = installed_observer
    select(fixture, "claude")
    bundle = tmp_path / "installed-workspace"
    shutil.copytree(fixture["desired"].bundle_path("manifest-workspace"), bundle)
    record_path = fixture["record"]
    original_record = record_path.read_bytes()
    original_receipt = fixture["receipt"].read_bytes()
    displaced = None
    changed_file = None
    try:
        displaced, changed_file = _apply_installed_failure(
            fixture, bundle, failure, record_path, original_record, original_receipt
        )
        _assert_installed_failure_is_read_only(
            fixture, tmp_path, bundle, entrypoint, failure
        )
    finally:
        if displaced is not None:
            displaced.rename(fixture["desired"].release_root)
        record_path.write_bytes(original_record)
        if changed_file is not None:
            changed_file[0].write_bytes(changed_file[1])
        fixture["receipt"].write_bytes(original_receipt)


def _apply_installed_failure(
    fixture, bundle, failure, record_path, original_record, original_receipt
):
    from manifest_agent.observer_runtime_identity import sign

    displaced = None
    changed_file = None
    if failure == "missing":
        record_path.unlink()
    elif failure in {"stale", "wrong-binding"}:
        receipt = json.loads(original_receipt)
        receipt["source_commit" if failure == "stale" else "archive_sha256"] = "f" * 64
        fixture["receipt"].write_bytes(canonical(receipt))
    elif failure == "provider":
        record = json.loads(original_record)
        record["provider"]["exe_sha256"] = "0" * 64
        record_path.write_bytes(
            canonical(sign(record, observer_key_path(fixture["env"])))
        )
    elif failure == "record-proof":
        record = json.loads(original_record)
        record["proof"] = "0" * 64
        record_path.write_bytes(canonical(record))
    elif failure == "runtime-file":
        record = json.loads(original_record)
        relative = next(
            name
            for name, row in record["files"].items()
            if name.endswith(".py") and row["kind"] == "file"
        )
        path = fixture["environment"] / relative
        changed_file = (path, path.read_bytes())
        path.write_bytes(b"changed installed runtime bytes")
    elif failure == "tampered":
        (bundle / "runtime/observer/uv.lock").write_text("changed")
    else:
        release = fixture["desired"].release_root
        displaced = release.with_name(release.name + "-missing-contracts")
        release.rename(displaced)
    return displaced, changed_file


def _assert_installed_failure_is_read_only(
    fixture, tmp_path, bundle, entrypoint, failure
):
    env = dict(fixture["env"])
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONDONTWRITEBYTECODE"):
        env.pop(name, None)
    protected = [
        bundle,
        *runtime_roots(env),
        Path(env["XDG_CACHE_HOME"]),
        fixture["receipt"].parent,
    ]
    before = [inventory(path) for path in protected]
    result = subprocess.run(
        isolated_public_command(
            [
                str(Path(sys.executable).resolve()),
                str(bundle / "skills" / entrypoint),
                "--json",
                "--receipt",
                str(fixture["receipt"]),
            ],
            fixture,
        ),
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] not in {"ok", "converged"}, report
    if failure != "contracts":
        assert report["native_observed"] is False, report
    assert [inventory(path) for path in protected] == before
