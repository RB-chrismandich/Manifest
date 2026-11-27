"""Deploy-reconcile and cross-entrypoint native-evidence tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from manifest_agent.models import (
    MarketplaceSource,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.release import ResolvedRelease
from manifest_agent.service import ManifestService
from tests.python.manifest_agent._installed_observer_fixtures import (
    installed_observer as _installed_observer,
)
from tests.python.manifest_agent._omp_native_fixture import make_adapter
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    _harness_receipt,
    _isolated_env,
    _run,
    _valid_receipt,
    _with_omp_fixture,
)
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    repo_root as _repo_root,  # noqa: F401 - register the pytest fixture
)
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    workspace_bundle as _workspace_bundle_fixture,  # noqa: F401 - register the pytest fixture
)

installed_observer = _installed_observer

_BUNDLES = (
    "manifest-code-quality",
    "manifest-docs",
    "manifest-forge",
    "manifest-ops",
    "manifest-security",
    "manifest-spec-planning",
    "manifest-workspace",
    "stitch-design",
)


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        item.relative_to(root).as_posix(): (
            item.read_bytes() if item.is_file() else None
        )
        for item in root.rglob("*")
    }


def _malformed_native_report(
    workspace_bundle: Path,
    tmp_path: Path,
    entrypoint: str,
    native_errors: object,
    native_state: str = "READY",
) -> Any:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    receipt = _valid_receipt({"omp": _harness_receipt("omp", list(_BUNDLES))})
    (state_root / "installation.json").write_text(json.dumps(receipt), encoding="utf-8")
    record = {
        "state": native_state,
        "verified": True,
        "converged": True,
        "version": "1.0",
        "installed_plugin_ids": list(_BUNDLES),
        "capabilities": {},
        "components": {"bundles": list(_BUNDLES)},
        "errors": [],
        "warnings": [],
    }
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {
                "operation": "reconcile",
                "harnesses": {"omp": record},
                "errors": native_errors,
            }
        ),
        encoding="utf-8",
    )
    filename = "env_check.py" if entrypoint == "env-check" else "plugin_reconcile.py"
    script = workspace_bundle / "skills" / entrypoint / "scripts" / filename
    result = _run(
        script,
        "--json",
        "--native-evidence",
        str(native),
        env=env,
        cwd=tmp_path,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("entrypoint", ("env-check", "deploy-reconcile"))
def test_entrypoints_reject_converged_drifted_native_evidence(
    workspace_bundle: Path, tmp_path: Path, entrypoint: str
) -> None:
    report = _malformed_native_report(
        workspace_bundle,
        tmp_path,
        entrypoint,
        native_errors=[],
        native_state="DRIFTED",
    )

    if entrypoint == "env-check":
        assert report["status"] == "degraded"
        observed = report["harnesses"]["omp"]["observed"]
        assert observed["state"] == "DRIFTED"
        assert observed["verified"] is True
        assert observed["converged"] is True
        assert "DRIFTED state cannot be converged" in observed["validation_errors"]
    else:
        assert report["status"] != "converged"
        assert report["repair_required"] is True
        assert any(
            "DRIFTED state cannot be converged" in item["reason"]
            for item in report["drift"]
        )


def test_deploy_reconcile_empty_receipt_never_converges(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(_valid_receipt({})), encoding="utf-8")
    script = workspace_bundle / "skills/deploy-reconcile/scripts/plugin_reconcile.py"

    result = _run(script, "--json", env=env, cwd=tmp_path)

    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["repair_required"] is True
    assert report["native_observed"] is False


def test_receipt_bound_reconcile_renders_missing_receipt_diagnostics(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    script = workspace_bundle / "skills/deploy-reconcile/scripts/plugin_reconcile.py"
    env = _isolated_env(tmp_path)
    receipt = tmp_path / "absent.json"
    result = _run(script, "--receipt", str(receipt), env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "all: unverified - installation receipt is absent" in result.stdout
    assert "repair required" in result.stdout

    result = _run(script, "--receipt", str(receipt), "--json", env=env, cwd=tmp_path)
    assert json.loads(result.stdout)["unverified"] == [
        {"harness": "all", "reason": "installation receipt is absent"}
    ]


@pytest.mark.parametrize(
    "missing_field",
    ("state", "version", "components", "capabilities", "warnings"),
)
def test_deploy_reconcile_incomplete_native_records_never_converge(
    workspace_bundle: Path, tmp_path: Path, missing_field: str
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    bundles = [
        "manifest-code-quality",
        "manifest-docs",
        "manifest-forge",
        "manifest-ops",
        "manifest-security",
        "manifest-spec-planning",
        "manifest-workspace",
        "stitch-design",
    ]
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", bundles)})),
        encoding="utf-8",
    )
    record = {
        "state": "READY",
        "verified": True,
        "converged": True,
        "version": "1.0",
        "installed_plugin_ids": bundles,
        "components": {"bundles": bundles},
        "capabilities": {},
        "errors": [],
        "warnings": [],
    }
    del record[missing_field]
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {"operation": "reconcile", "harnesses": {"omp": record}, "errors": []}
        ),
        encoding="utf-8",
    )

    result = _run(
        workspace_bundle / "skills/deploy-reconcile/scripts/plugin_reconcile.py",
        "--json",
        "--native-evidence",
        str(native),
        env=env,
        cwd=tmp_path,
    )

    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["repair_required"] is True
    assert any(missing_field in item["reason"] for item in report["drift"])


@pytest.mark.parametrize("state", ([], {}))
def test_deploy_reconcile_rejects_unhashable_native_state(
    workspace_bundle: Path, tmp_path: Path, state: object
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    bundles = [
        "manifest-code-quality",
        "manifest-docs",
        "manifest-forge",
        "manifest-ops",
        "manifest-security",
        "manifest-spec-planning",
        "manifest-workspace",
        "stitch-design",
    ]
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", bundles)})),
        encoding="utf-8",
    )
    record = {
        "state": state,
        "verified": True,
        "converged": True,
        "version": "1.0",
        "installed_plugin_ids": bundles,
        "capabilities": {},
        "components": {"bundles": bundles},
        "errors": [],
        "warnings": [],
    }
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {"operation": "reconcile", "harnesses": {"omp": record}, "errors": []}
        ),
        encoding="utf-8",
    )

    result = _run(
        workspace_bundle / "skills/deploy-reconcile/scripts/plugin_reconcile.py",
        "--json",
        "--native-evidence",
        str(native),
        env=env,
        cwd=tmp_path,
    )

    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["repair_required"] is True
    assert any(
        "state must be READY, DEGRADED, BLOCKED, or DRIFTED" in item["reason"]
        for item in report["drift"]
    )


def test_deploy_reconcile_uses_native_omp_evidence(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    bundles = [
        "manifest-code-quality",
        "manifest-docs",
        "manifest-forge",
        "manifest-ops",
        "manifest-security",
        "manifest-spec-planning",
        "manifest-workspace",
        "stitch-design",
    ]
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", bundles)})),
        encoding="utf-8",
    )
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {
                "operation": "reconcile",
                "harnesses": {
                    "omp": {
                        "state": "READY",
                        "verified": True,
                        "converged": True,
                        "version": "1.0",
                        "installed_plugin_ids": bundles,
                        "components": {"bundles": bundles},
                        "capabilities": {},
                        "errors": [],
                        "warnings": [],
                    }
                },
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        workspace_bundle / "skills/deploy-reconcile/scripts/plugin_reconcile.py",
        "--json",
        "--native-evidence",
        str(native),
        env=env,
        cwd=tmp_path,
    )

    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["status"] == "converged"
    assert report["native_observed"] is True
    assert report["harnesses"]["omp"]["observed"]["verified"] is True
    assert report["authentication"] == "not_tested"


@pytest.mark.parametrize("entrypoint", ("env-check", "deploy-reconcile"))
@pytest.mark.parametrize("native_errors", (None, {}, [1], "invalid"))
def test_rejects_malformed_native_envelope_errors(
    workspace_bundle: Path,
    tmp_path: Path,
    entrypoint: str,
    native_errors: object,
) -> None:
    report = _malformed_native_report(
        workspace_bundle, tmp_path, entrypoint, native_errors
    )
    assert report["status"] == "degraded"
    if entrypoint == "env-check":
        assert any(
            "native evidence errors must be a list of strings" in warning
            for warning in report["warnings"]
        )
    else:
        assert report["repair_required"] is True
        assert any(
            "native evidence errors must be a list of strings" in item["reason"]
            for item in report["drift"]
        )


def _prepare_observer_fixture(tmp_path, runtime_context, fixture, monkeypatch):
    desired = fixture["desired"]
    env = _with_omp_fixture(
        {**fixture["env"], "HOME": str(tmp_path / "home")},
        tmp_path,
        version="omp 18.6.1",
    )
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    adapter, runner = make_adapter(tmp_path)
    state_root = fixture["receipt"].parent
    root, _source, resolved = _observer_release_context(
        desired, runtime_context, fixture
    )
    service = ManifestService(
        source=root,
        harnesses=("omp",),
        adapters={"omp": adapter},
        receipt_path=state_root
        / f"{tmp_path.name}-{runtime_context}-installation.json",
        release_resolver=lambda _selector: resolved,
    )
    result = service.install()
    assert result.state is ResultState.READY, result
    receipt = json.loads(service.receipt_path.read_text())
    assert receipt["harnesses"]["omp"]["owned_entries"]
    # The installed case launches from OMP's actual owned package cache.
    if runtime_context == "installed":
        bundle = Path(
            next(
                entry["target_path"]
                for entry in receipt["harnesses"]["omp"]["owned_entries"]
                if entry["identifier"] == "manifest-workspace@manifest"
            )
        )
    else:
        bundle = root / "plugins/manifest-workspace"
    return (
        env,
        state_root,
        Path(env["XDG_CACHE_HOME"]),
        bundle,
        runner,
        service.receipt_path,
    )


def _observer_release_context(desired, runtime_context, fixture):
    root = (
        fixture["base"] / "unavailable-source"
        if runtime_context == "repository"
        else desired.release_root
    )
    source = (
        MarketplaceSource(MarketplaceSourceKind.LOCAL, str(root), None)
        if runtime_context == "repository"
        else desired.marketplace_source
    )
    resolved = ResolvedRelease(
        desired.release_version,
        desired.source_commit,
        str(root),
        source,
        root,
        desired.repository_url,
        False,
        desired.archive_sha256,
    )
    return root, source, resolved


@pytest.mark.parametrize("entrypoint", ("env-check", "deploy-reconcile"))
@pytest.mark.parametrize("runtime_context", ("repository", "installed"))
def test_entrypoints_observe_native_state_through_packaged_cli(
    workspace_bundle: Path,
    repo_root: Path,
    tmp_path: Path,
    entrypoint: str,
    runtime_context: str,
    installed_observer,
    monkeypatch,
) -> None:
    env, state_root, cache_root, bundle, runner, receipt_path = (
        _prepare_observer_fixture(
            tmp_path, runtime_context, installed_observer, monkeypatch
        )
    )
    state_before = _tree_snapshot(state_root)
    cache_before = _tree_snapshot(cache_root)
    filename = "env_check.py" if entrypoint == "env-check" else "plugin_reconcile.py"
    script = bundle / "skills" / entrypoint / "scripts" / filename

    completed = _run(
        script, "--json", "--receipt", str(receipt_path), env=env, cwd=tmp_path
    )
    report = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stderr
    assert report["native_observed"] is True
    observed = report["harnesses"]["omp"]["observed"]
    assert observed["present"] is True
    assert observed["components"] is not None
    assert observed["version"] == "omp 18.6.1"
    assert observed["validation_errors"] == []
    assert report["harnesses"]["omp"]["authentication"] == "not_tested"
    assert any(command[1:3] == ("plugin", "list") for command in runner.calls)
    assert _tree_snapshot(state_root) == state_before
    assert _tree_snapshot(cache_root) == cache_before
