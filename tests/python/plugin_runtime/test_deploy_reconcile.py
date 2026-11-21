"""Deploy-reconcile and cross-entrypoint native-evidence tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from manifest_agent.models import (
    MarketplaceSource,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.release import ResolvedRelease, deterministic_tree_sha256
from manifest_agent.service import ManifestService
from tests.python.manifest_agent._omp_native_fixture import make_adapter
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    _harness_receipt,
    _isolated_env,
    _run,
    _valid_receipt,
    _with_manifest_cli,
    _with_omp_fixture,
)
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    repo_root as _repo_root,  # noqa: F401 - register the pytest fixture
)
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    workspace_bundle as _workspace_bundle_fixture,  # noqa: F401 - register the pytest fixture
)

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


def _copy_installed_workspace_scripts(workspace_bundle: Path, tmp_path: Path) -> Path:
    installed = tmp_path / "installed" / "manifest-workspace"
    for skill in ("env-check", "deploy-reconcile"):
        shutil.copytree(
            workspace_bundle / "skills" / skill,
            installed / "skills" / skill,
        )
    return installed


def _cache_release_for_installed_bundle(
    repo_root: Path, env: dict[str, str], receipt: dict[str, Any]
) -> None:
    version = "1.0.0"
    archive = b"read-only native observation fixture"
    checksum = hashlib.sha256(archive).hexdigest()
    receipt["release_version"] = version
    receipt["archive_sha256"] = checksum
    release_name = f"{version}-{checksum[:16]}"
    release_root = Path(env["XDG_CACHE_HOME"]) / "manifest" / "releases" / release_name
    release_root.mkdir(parents=True)
    (release_root.parent / f"{release_name}.tar.gz").write_bytes(archive)
    shutil.copytree(repo_root / "plugins", release_root / "plugins")
    marketplace = repo_root / ".claude-plugin"
    if marketplace.is_dir():
        shutil.copytree(marketplace, release_root / ".claude-plugin")


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


def _observer_service(
    repo_root: Path,
    env: dict[str, str],
    state_root: Path,
    adapter: Any,
    runtime_context: str,
) -> ManifestService:
    if runtime_context == "repository":
        resolved = ResolvedRelease(
            f"local-{repo_root.name}",
            "a" * 40,
            str(repo_root),
            MarketplaceSource(MarketplaceSourceKind.LOCAL, str(repo_root), None),
            repo_root,
            "https://github.com/RB-chrismandich/Manifest",
            True,
            deterministic_tree_sha256(repo_root),
        )
    else:
        release_identity = {"release_version": "1.0.0"}
        _cache_release_for_installed_bundle(repo_root, env, release_identity)
        release_root = (
            Path(env["XDG_CACHE_HOME"])
            / "manifest"
            / "releases"
            / f"{release_identity['release_version']}-{release_identity['archive_sha256'][:16]}"
        )
        resolved = ResolvedRelease(
            "1.0.0",
            "a" * 40,
            "cached test release",
            MarketplaceSource(
                MarketplaceSourceKind.GIT,
                "https://example.invalid/Manifest.git",
                "a" * 40,
            ),
            release_root,
            "https://example.invalid/Manifest",
            False,
            release_identity["archive_sha256"],
        )
    return ManifestService(
        source=repo_root,
        harnesses=("omp",),
        adapters={"omp": adapter},
        receipt_path=state_root / "installation.json",
        release_resolver=lambda _selector: resolved,
    )


def _prepare_observer_fixture(
    workspace_bundle: Path,
    repo_root: Path,
    tmp_path: Path,
    runtime_context: str,
) -> tuple[dict[str, str], Path, Path, Path, Any]:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path, version="omp 18.6.1")
    env["XDG_DATA_HOME"] = ""
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    adapter, runner = make_adapter(tmp_path)
    service = _observer_service(repo_root, env, state_root, adapter, runtime_context)
    assert service.install().state is ResultState.READY
    receipt = json.loads((state_root / "installation.json").read_text(encoding="utf-8"))
    assert receipt["harnesses"]["omp"]["owned_entries"]
    bundle = (
        _copy_installed_workspace_scripts(workspace_bundle, tmp_path)
        if runtime_context == "installed"
        else workspace_bundle
    )
    return env, state_root, Path(env["XDG_CACHE_HOME"]), bundle, runner


@pytest.mark.parametrize("entrypoint", ("env-check", "deploy-reconcile"))
@pytest.mark.parametrize("runtime_context", ("repository", "installed"))
def test_entrypoints_observe_native_state_through_packaged_cli(
    workspace_bundle: Path,
    repo_root: Path,
    tmp_path: Path,
    entrypoint: str,
    runtime_context: str,
) -> None:
    env, state_root, cache_root, bundle, runner = _prepare_observer_fixture(
        workspace_bundle, repo_root, tmp_path, runtime_context
    )
    env = _with_manifest_cli(env, tmp_path, repo_root)
    state_before = _tree_snapshot(state_root)
    cache_before = _tree_snapshot(cache_root)
    filename = "env_check.py" if entrypoint == "env-check" else "plugin_reconcile.py"
    script = bundle / "skills" / entrypoint / "scripts" / filename

    completed = _run(script, "--json", env=env, cwd=tmp_path)
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
