"""Archived adapter layout round-trip scenarios."""

from manifest_agent.observer_runtime_identity import bundle_tree_sha256
from tests.python.manifest_agent._installed_observer_fixtures import (
    HARNESSES,
    Path,
    canonical,
    digest,
    installation_lock,
    inventory,
    isolated_public_command,
    json,
    os,
    provision,
    pytest,
    replace,
    runtime,
    runtime_roots,
    subprocess,
    sys,
    write_receipt_atomic,
)


@pytest.mark.parametrize("harness", HARNESSES)
def test_archived_adapter_layout_roundtrip_matches_installed_public_observation(
    installed_observer, tmp_path, monkeypatch, harness
):
    """Keep real adapters/contracts/layouts; substitute only the native IO boundary."""
    fixture = installed_observer
    desired, environment, adapter, marketplace_root, native = _prepare_layout_adapter(
        fixture, tmp_path, monkeypatch, harness
    )
    detected, installed, _ = _install_layout_adapter(adapter, desired, harness)
    _prepare_codex_observer_runtime(fixture, desired, harness, monkeypatch)
    receipt, direct = _record_layout_observation(
        fixture, desired, harness, adapter, detected, installed, marketplace_root
    )
    bundle, protected, poison = _prepare_public_bundle(
        fixture, desired, environment, harness, tmp_path, receipt
    )
    _assert_public_observations(
        fixture, tmp_path, environment, bundle, harness, direct, protected
    )
    assert not (poison / "__pycache__").exists()
    _inject_native_inventory_disagreement(native, harness, desired, environment)
    _assert_public_drift(fixture, tmp_path, environment, bundle, harness, protected)


def _prepare_public_bundle(fixture, desired, environment, harness, tmp_path, receipt):
    from manifest_agent.state import read_receipt

    poison = tmp_path / "manifest_agent"
    poison.mkdir()
    (poison / "__init__.py").write_text(
        'raise RuntimeError("checkout import forbidden")\n'
    )
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPYCACHEPREFIX",
    ):
        environment.pop(name, None)
    guard_bin = tmp_path / "no-installers"
    guard_bin.mkdir()
    (guard_bin / "python3").symlink_to(Path(sys.executable).resolve())
    for name in ("manifest", "uv", "uvx", "pip", "pip3", "curl", "wget"):
        executable = guard_bin / name
        executable.write_text(
            "#!/bin/sh\necho forbidden-tool-invocation >&2\nexit 97\n"
        )
        executable.chmod(0o755)
    environment["PATH"] = str(guard_bin) + os.pathsep + environment["PATH"]
    bundle = desired.bundle_path("manifest-workspace")
    workspace_version = next(
        c.version for c in desired.contracts if c.name == "manifest-workspace"
    )
    if harness in {"claude", "codex"}:
        bundle = (
            Path(environment["HOME"])
            / f".{harness}/plugins/cache/manifest/manifest-workspace"
            / workspace_version
        )
    elif harness == "omp":
        owned = read_receipt(fixture["receipt"]).harnesses["omp"]
        bundle = Path(
            next(
                entry.target_path
                for entry in owned.owned_entries
                if entry.identifier == "manifest-workspace@manifest"
            )
        )
    elif harness == "antigravity":
        bundle = Path(environment["HOME"]) / ".gemini/config/plugins/manifest-workspace"
    assert (bundle / "runtime/observer/observe.py").is_file()
    assert bundle_tree_sha256(bundle) == receipt.bundle_checksums["manifest-workspace"]
    protected = [
        fixture["environment"],
        *runtime_roots(environment),
        desired.release_root,
        Path(environment["HOME"]),
        fixture["receipt"].parent,
        Path(environment["XDG_CACHE_HOME"]),
        Path(environment["XDG_CONFIG_HOME"]),
    ]
    return bundle, protected, poison


def _assert_public_observations(
    fixture, tmp_path, environment, bundle, harness, direct, protected
):
    for entrypoint in (
        "env-check/scripts/env_check.py",
        "deploy-reconcile/scripts/plugin_reconcile.py",
    ):
        before = [inventory(path) for path in protected]
        launched = subprocess.run(
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
            env=environment,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert launched.stdout, launched.stderr
        observed = json.loads(launched.stdout)
        assert observed["native_observed"] is True, observed
        assert set(observed["harnesses"]) == {harness}
        native_observed = observed["harnesses"][harness]["observed"]
        assert isinstance(native_observed, dict), observed
        assert direct["harnesses"][harness]["verified"] == native_observed["verified"]
        assert direct["harnesses"][harness]["state"] == native_observed["state"]
        assert set(direct["harnesses"][harness]["installed_plugin_ids"]) == set(
            native_observed["installed_plugin_ids"]
        )
        assert [inventory(path) for path in protected] == before
        assert "forbidden-tool-invocation" not in launched.stderr


def _inject_native_inventory_disagreement(native, harness, desired, environment):
    # Inject native inventory disagreement through fixture protocol IO, never
    # by handing fabricated observation JSON to either consumer.
    if harness == "omp":
        registry = Path(environment["HOME"]) / ".omp/plugins/installed_plugins.json"
        document = json.loads(registry.read_bytes())
        document["plugins"] = {}
        registry.write_bytes(canonical(document))
    else:
        changed = json.loads(native._responses(harness, desired, "removed"))
        changed["responses"].append(native._response(["--version"], "0.2.0\n"))
        environment["HARNESS_STUB_RESPONSES"] = json.dumps(changed)


def _assert_public_drift(fixture, tmp_path, environment, bundle, harness, protected):
    for entrypoint in (
        "env-check/scripts/env_check.py",
        "deploy-reconcile/scripts/plugin_reconcile.py",
    ):
        before = [inventory(path) for path in protected]
        drifted = subprocess.run(
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
            env=environment,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(drifted.stdout)
        assert report["native_observed"] is True, report
        assert report["status"] not in {"ok", "converged"}, report
        assert [inventory(path) for path in protected] == before


def _prepare_layout_adapter(fixture, tmp_path, monkeypatch, harness):
    import shutil

    from manifest_agent.adapters.omp import OmpAdapter
    from tests.python.manifest_agent import test_native_adapter_integration as native
    from tests.python.manifest_agent._omp_native_fixture import NativeRunner
    from tests.python.plugin_runtime.workspace_runtime_helpers import _with_omp_fixture

    desired = replace(fixture["desired"], requested_harnesses=(harness,))
    environment = {**fixture["env"], "HOME": str(tmp_path / "home")}
    Path(environment["HOME"]).mkdir()
    monkeypatch.setattr(native, "_REPOSITORY", desired.release_root)
    if harness == "omp":
        environment = _with_omp_fixture(environment, tmp_path, version="18.6.1")
        environment.update(
            OMP_PROFILE="", PI_PROFILE="", PI_CONFIG_DIR=".omp", PI_CODING_AGENT_DIR=""
        )
        adapter = OmpAdapter(
            NativeRunner(),
            which=lambda name: shutil.which(name, path=environment["PATH"]),
            env=environment,
            cwd=tmp_path,
        )
        marketplace_root = None
    else:
        desired, environment, adapter, marketplace_root = _configure_non_omp_adapter(
            native, desired, environment, tmp_path, harness
        )
    bind = getattr(adapter, "bind_ownership_authority", None)
    if bind is not None:
        bind(fixture["receipt"].parent / "ownership.key")
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    return desired, environment, adapter, marketplace_root, native


def _configure_non_omp_adapter(native, desired, environment, tmp_path, harness):
    import shutil

    configured = native._configured_environment(tmp_path, harness, desired)
    environment.update(configured)
    for executable in (tmp_path / "bin").iterdir():
        if executable.is_symlink():
            payload = executable.read_bytes()
            executable.unlink()
            executable.write_bytes(payload)
            executable.chmod(0o755)
    responses = json.loads(native._responses(harness, desired, "installed"))
    marketplace_root = None
    if harness == "codex":
        desired, marketplace_root = _configure_codex_responses(
            desired, responses, tmp_path
        )
    if harness == "antigravity":
        for contract in desired.contracts:
            shutil.copytree(
                desired.bundle_path(contract.name),
                Path(environment["HOME"]) / ".gemini/config/plugins" / contract.name,
            )
    if harness == "claude":
        native_root = Path(environment["HOME"]) / ".claude/plugins/cache/manifest"
        for contract in desired.contracts:
            shutil.copytree(
                desired.bundle_path(contract.name),
                native_root / contract.name / contract.version,
            )
        for response in responses["responses"]:
            if response.get("argv") == ["plugin", "list", "--json"]:
                rows = json.loads(response["stdout"])
                for row in rows:
                    row["installPath"] = str(
                        native_root / row["id"].split("@")[0] / row["version"]
                    )
                response["stdout"] = json.dumps(rows)
    environment["HARNESS_STUB_RESPONSES"] = json.dumps(responses)
    return desired, environment, native._adapter(harness, environment), marketplace_root


def _configure_codex_responses(desired, responses, tmp_path):
    from manifest_agent.models import MarketplaceSource, MarketplaceSourceKind

    marketplace_root, commit = _initialize_codex_marketplace(desired, tmp_path)
    desired = replace(
        desired,
        source_commit=commit,
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.GIT,
            desired.marketplace_source.source,
            commit,
        ),
    )
    _rewrite_codex_responses(responses, desired, marketplace_root)
    return desired, marketplace_root


def _initialize_codex_marketplace(desired, tmp_path):
    import shutil

    marketplace_root = tmp_path / "native-marketplace"
    shutil.copytree(desired.release_root, marketplace_root, symlinks=True)
    subprocess.run(
        ["git", "-C", str(marketplace_root), "init"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(marketplace_root), "add", "."],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Manifest Test",
            "-c",
            "user.email=manifest@example.invalid",
            "-C",
            str(marketplace_root),
            "commit",
            "-m",
            "installed Codex fixture",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(marketplace_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return marketplace_root, commit


def _rewrite_codex_responses(responses, desired, marketplace_root):
    from manifest_agent.adapters.codex_marketplace import marketplace_add_argv

    for response in responses["responses"]:
        argv = response.get("argv", [])
        if argv[:3] == ["plugin", "marketplace", "add"]:
            response["argv"] = list(marketplace_add_argv(desired))[1:]
        elif argv == ["plugin", "marketplace", "list", "--json"]:
            response["stdout"] = json.dumps(
                {
                    "marketplaces": [
                        {
                            "name": "manifest",
                            "root": str(marketplace_root),
                            "marketplaceSource": {
                                "sourceType": "git",
                                "source": desired.marketplace_source.source,
                            },
                        }
                    ]
                }
            )


def _install_layout_adapter(adapter, desired, harness):
    from manifest_agent.service_state import operation_desired_state

    detected = adapter.detect()
    assert detected.present, detected.reason
    installed = adapter.install(desired)
    inspected = adapter.inspect(operation_desired_state(desired, adapter, installed))
    # Installation evidence must name the complete declared domain set. No
    # component/capability requirements are stripped from these contracts.
    expected_names = {contract.name for contract in desired.contracts}
    if harness == "cursor":
        assert installed.capabilities.get("marketplace:manifest") == "verified"
        assert any(
            "activat" in reason.lower()
            for reason in (*installed.errors, *installed.warnings)
        )
    else:
        assert {
            name.split("@", 1)[0] for name in installed.installed_plugin_ids
        } == expected_names, installed
        assert {
            name.split("@", 1)[0] for name in inspected.installed_plugin_ids
        } == expected_names, inspected
    return detected, installed, inspected


def _prepare_codex_observer_runtime(fixture, desired, harness, monkeypatch):
    if harness != "codex":
        return
    project = desired.release_root / runtime.PROJECT
    pin = json.loads((project / "uv-toolchain.lock.json").read_bytes())["tools"]["uv"][
        "platforms"
    ][runtime.platform_id()]
    archive = fixture["uv_archive"].read_bytes()

    def locked_fetch(url):
        assert url == pin["url"]
        assert digest(archive) == pin["sha256"]
        return archive

    monkeypatch.setattr(
        runtime,
        "provision",
        lambda *args, **kwargs: provision(*args, **kwargs, fetcher=locked_fetch),
    )
    # The installed_observer fixture keeps its offline wrapper active through yield.
    with installation_lock(fixture["receipt"].parent / "install.lock"):
        runtime.prepare_observer_runtime(desired, receipt_path=fixture["receipt"])


def _record_layout_observation(
    fixture, desired, harness, adapter, detected, installed, marketplace_root
):
    from manifest_agent.native_observation import observe_native_state
    from manifest_agent.service_state import build_receipt
    from manifest_agent.state import read_receipt

    receipt = build_receipt(
        desired,
        {harness: installed},
        {harness: detected},
        {harness: adapter},
        HARNESSES,
    )
    write_receipt_atomic(fixture["receipt"], receipt)
    assert set(read_receipt(fixture["receipt"]).harnesses) == {harness}
    if harness == "codex":
        head = subprocess.run(
            ["git", "-C", str(marketplace_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert read_receipt(fixture["receipt"]).source_commit == head
    direct = observe_native_state(receipt_path=fixture["receipt"])
    assert set(direct["harnesses"]) == {harness}
    assert direct["errors"] == []
    return receipt, direct
