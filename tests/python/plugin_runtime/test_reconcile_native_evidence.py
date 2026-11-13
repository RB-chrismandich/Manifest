"""Typed producer fixtures for native package/component reconciliation.

Wire producers: src/manifest_agent/models.py:151-188 and
src/manifest_agent/adapters/omp_inspection.py:96-154,187-234,327-379.
These fixtures exercise serialization, not live activation qualification.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from manifest_agent.models import (
    NativeComponentInspection,
    NativeInspection,
    NativePluginInspection,
    ResultState,
)
from tests.python.manifest_agent._omp_native_fixture import (
    get_json,
    make_adapter,
    make_desired,
    make_service,
    put_json,
)

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "plugins/manifest-workspace/skills/deploy-reconcile/scripts/plugin_reconcile.py"
)
spec = importlib.util.spec_from_file_location("reconciler", SCRIPT)
reconciler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconciler)


def package(name, status="verified"):
    return NativePluginInspection(
        name + "@manifest",
        name,
        "manifest",
        None,
        "native-local-marketplace",
        "0.1.0",
        "user",
        status != "disabled",
        "/native",
        "/native/" + name,
        status,
    )


@pytest.mark.parametrize(
    "component,status,diagnostic",
    [
        ("resolved", "converged", False),
        ("unresolved", "drift", False),
        ("unobserved", "degraded", False),
        ("unsupported", "degraded", False),
        ("resolved", "drift", True),
    ],
)
def test_fresh_cli_preserves_component_and_typed_package_evidence(
    tmp_path, component, status, diagnostic
):
    state = tmp_path / "state"
    receipt = state / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {"harnesses": {"omp": {"plugins": sorted(reconciler.EXPECTED_BUNDLES)}}}
        )
    )
    packages = tuple(
        package(name, "missing" if diagnostic else "verified")
        for name in sorted(reconciler.EXPECTED_BUNDLES)
    )
    native = NativeInspection(
        "omp",
        "user",
        "/native",
        packages,
        (
            NativeComponentInspection(
                "skill",
                "delegate",
                component,
                "native-resolver",
                "/native/delegate/SKILL.md" if component == "resolved" else None,
            ),
        ),
        "verified",
        ("missing required plugin",) if diagnostic else (),
    )
    source = tmp_path / "inspection.json"
    source.write_text(
        json.dumps(
            {
                "harnesses": {
                    "omp": {
                        "state": "DRIFTED" if diagnostic else "READY",
                        "native_inspection": asdict(native),
                    }
                }
            }
        )
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--native-inspection", str(source)],
        env=dict(os.environ, XDG_STATE_HOME=str(state)),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == status, report
    if diagnostic:
        assert any("missing:" in item["reason"] for item in report["drift"])


def test_unreadable_producer_does_not_fabricate_missing_packages():
    native = NativeInspection(
        "omp", "user", "/native", inventory_errors=("OMP plugin list failed",)
    )
    packages, error = reconciler._native_packages(
        {"native_inspection": json.loads(json.dumps(asdict(native)))}
    )
    assert packages is None
    assert "unreadable" in error


@pytest.mark.parametrize(
    "state,expected",
    [
        ("missing", "missing:"),
        ("disabled", "disabled:"),
        ("inconsistent", "stale:"),
    ],
)
def test_observed_package_drift_keeps_its_type(state, expected):
    row = json.loads(json.dumps(asdict(package("manifest-delegate", state))))
    drift = reconciler._compare(
        "omp", {"manifest-delegate"}, {"manifest-delegate": row}
    )
    assert drift[0]["reason"].startswith(expected)
    extra = reconciler._compare("omp", set(), {"manifest-delegate": row})
    if state != "missing":
        assert extra


@pytest.mark.parametrize("contents", [None, "{malformed", '{"harnesses":{"omp":{}}}'])
def test_fresh_missing_or_malformed_observation_never_converges(tmp_path, contents):
    state = tmp_path / "state"
    receipt = state / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {"harnesses": {"omp": {"plugins": sorted(reconciler.EXPECTED_BUNDLES)}}}
        )
    )
    source = tmp_path / "inspection.json"
    if contents is not None:
        source.write_text(contents)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--native-inspection", str(source)],
        env=dict(os.environ, XDG_STATE_HOME=str(state)),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["verified"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("enabled", "false"),
        ("version", 1),
        ("install_path", 17),
    ],
)
def test_malformed_native_package_field_never_converges(tmp_path, field, value):
    state = tmp_path / "state"
    receipt = state / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {"harnesses": {"omp": {"plugins": sorted(reconciler.EXPECTED_BUNDLES)}}}
        )
    )
    packages = tuple(package(name) for name in sorted(reconciler.EXPECTED_BUNDLES))
    native = NativeInspection(
        "omp",
        "user",
        "/native",
        packages,
        (
            NativeComponentInspection(
                "skill",
                "delegate",
                "resolved",
                "native-resolver",
                "/native/delegate/SKILL.md",
            ),
        ),
        "verified",
    )
    document = json.loads(
        json.dumps(
            {
                "harnesses": {
                    "omp": {
                        "state": "READY",
                        "native_inspection": asdict(native),
                    }
                }
            }
        )
    )
    document["harnesses"]["omp"]["native_inspection"]["packages"][0][field] = value
    source = tmp_path / "inspection.json"
    source.write_text(json.dumps(document))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--native-inspection", str(source)],
        env=dict(os.environ, XDG_STATE_HOME=str(state)),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "degraded", report
    assert report["verified"] is False


def _install_unowned_plugin(adapter, desired):
    root = adapter._native_root()
    registry_path = root / "plugins/installed_plugins.json"
    lock_path = root / "plugins/omp-plugins.lock.json"
    registry = get_json(registry_path, {"version": 2, "plugins": {}})
    lock = get_json(lock_path, {"plugins": {}, "settings": {}})
    source_id = f"{desired.contracts[0].name}@manifest"
    source_row = registry["plugins"][source_id][0]
    extra_id = "manifest-extra@manifest"
    extra_package = "@manifest/manifest-extra"
    version = source_row["version"]
    extra_path = (
        root / "plugins/cache/plugins" / f"manifest___manifest-extra___{version}"
    )
    shutil.copytree(source_row["installPath"], extra_path)
    put_json(extra_path / "package.json", {"name": extra_package, "version": version})
    extra_link = root / "plugins/node_modules" / extra_package
    extra_link.parent.mkdir(parents=True, exist_ok=True)
    extra_link.symlink_to(extra_path)
    registry["plugins"][extra_id] = [{**source_row, "installPath": str(extra_path)}]
    lock["plugins"][extra_package] = {"version": version, "enabled": True}
    put_json(registry_path, registry)
    put_json(lock_path, lock)
    return extra_id


def _run_native_reconcile(tmp_path, desired, observed):
    report = {
        "harnesses": {
            "omp": {
                "state": observed.state.value.upper(),
                "native_inspection": json.loads(
                    json.dumps(asdict(observed.native_inspection))
                ),
            }
        }
    }
    state = tmp_path / "state"
    receipt = state / "manifest/installation.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "harnesses": {
                    "omp": {
                        "plugins": sorted(
                            contract.name for contract in desired.contracts
                        )
                    }
                }
            }
        )
    )
    source = tmp_path / "inspection.json"
    source.write_text(json.dumps(report))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--native-inspection",
            str(source),
        ],
        env=dict(os.environ, XDG_STATE_HOME=str(state)),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_full_native_manifest_inventory_reports_unowned_installed_package(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    assert service.install().state is ResultState.READY
    extra_id = _install_unowned_plugin(adapter, desired)

    observed = adapter.inspect(desired)
    assert observed.state is ResultState.READY
    assert any(
        item.package_id == extra_id and item.status == "verified"
        for item in observed.native_inspection.packages
    )
    reconciled = _run_native_reconcile(tmp_path, desired, observed)
    assert reconciled["status"] == "degraded", reconciled
    assert any(
        item["capability"] == "manifest-extra" and item["reason"].startswith("extra:")
        for item in reconciled["drift"]
    )


def test_malformed_component_path_never_converges(tmp_path):
    state = tmp_path / "state"
    receipt = state / "manifest/installation.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {"harnesses": {"omp": {"plugins": sorted(reconciler.EXPECTED_BUNDLES)}}}
        )
    )
    native = NativeInspection(
        "omp",
        "user",
        "/native",
        tuple(package(name) for name in sorted(reconciler.EXPECTED_BUNDLES)),
        (
            NativeComponentInspection(
                "skill",
                "delegate",
                "resolved",
                "native-resolver",
                "/native/delegate/SKILL.md",
            ),
        ),
        "verified",
    )
    document = json.loads(
        json.dumps(
            {
                "harnesses": {
                    "omp": {
                        "state": "READY",
                        "native_inspection": asdict(native),
                    }
                }
            }
        )
    )
    document["harnesses"]["omp"]["native_inspection"]["components"][0][
        "resolved_path"
    ] = 17
    source = tmp_path / "inspection.json"
    source.write_text(json.dumps(document))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--native-inspection", str(source)],
        env=dict(os.environ, XDG_STATE_HOME=str(state)),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "degraded", report
    assert report["verified"] is False


def test_unverified_inventory_takes_status_precedence_over_receipt_drift(tmp_path):
    state = tmp_path / "state"
    receipt = state / "manifest/installation.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"harnesses": {"omp": {"plugins": []}}}))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        env=dict(os.environ, XDG_STATE_HOME=str(state)),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "degraded", report
    assert report["verified"] is False
    assert report["repair_required"] is True
