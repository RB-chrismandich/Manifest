"""Receipt and native-observation isolation tests for the workspace bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_env_check_rejects_incomplete_and_empty_receipts(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    script = workspace_bundle / "skills/env-check/scripts/env_check.py"

    for document in ({"schema_version": 1, "harnesses": {}}, _valid_receipt({})):
        receipt.write_text(json.dumps(document), encoding="utf-8")
        result = _run(script, "--json", env=env, cwd=tmp_path)
        report = json.loads(result.stdout)
        assert report["status"] == "degraded"
        assert report["receipt"]["valid"] is False


@pytest.mark.parametrize(
    "mutate",
    (
        lambda receipt: receipt.pop("migration_backup"),
        lambda receipt: receipt.update(source_commit="bad"),
        lambda receipt: receipt.update(bundle_checksums={"x": "bad"}),
        lambda receipt: receipt["harnesses"]["omp"].update(harness="bogus"),
        lambda receipt: receipt["harnesses"]["omp"].update(owned_entries=[None]),
    ),
)
def test_env_check_rejects_receipts_invalid_under_coordinator_schema(
    workspace_bundle: Path, tmp_path: Path, mutate
) -> None:
    env = _isolated_env(tmp_path)
    state = Path(env["XDG_STATE_HOME"]) / "manifest"
    state.mkdir(parents=True)
    receipt_data = _valid_receipt({"omp": _harness_receipt("omp")})
    mutate(receipt_data)
    path = state / "installation.json"
    path.write_text(json.dumps(receipt_data), encoding="utf-8")
    result = _run(
        workspace_bundle / "skills/env-check/scripts/env_check.py",
        "--json",
        env=env,
        cwd=tmp_path,
    )
    assert json.loads(result.stdout)["status"] == "degraded"
    assert json.loads(result.stdout)["receipt"]["valid"] is False


@pytest.mark.parametrize("schema_version", [1.0, True])
def test_env_check_rejects_non_integer_receipt_schema_version(
    workspace_bundle: Path, tmp_path: Path, schema_version: object
) -> None:
    env = _isolated_env(tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    receipt = _valid_receipt({"omp": _harness_receipt("omp", ["bundle"])})
    receipt["schema_version"] = schema_version
    (state_root / "installation.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = _run(
        workspace_bundle / "skills/env-check/scripts/env_check.py",
        "--json",
        env=env,
        cwd=tmp_path,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["receipt"]["valid"] is False


def test_env_check_rejects_nonconverged_native_despite_matching_inventory(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    state = Path(env["XDG_STATE_HOME"]) / "manifest"
    state.mkdir(parents=True)
    (state / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", ["bundle"])})),
        encoding="utf-8",
    )
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {
                "operation": "reconcile",
                "harnesses": {
                    "omp": {
                        "state": "DEGRADED",
                        "verified": True,
                        "converged": False,
                        "version": "1.0",
                        "installed_plugin_ids": ["bundle"],
                        "components": {},
                        "capabilities": {},
                        "errors": ["native failure"],
                        "warnings": [],
                    }
                },
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        workspace_bundle / "skills/env-check/scripts/env_check.py",
        "--json",
        "--native-evidence",
        str(native),
        env=env,
        cwd=tmp_path,
    )
    report = json.loads(result.stdout)
    assert any(
        "native inspection did not converge" in warning
        for warning in report["warnings"]
    )
    assert report["harnesses"]["omp"]["observed"]["errors"] == ["native failure"]


@pytest.mark.parametrize(
    "missing_field",
    ("state", "version", "components", "capabilities", "warnings"),
)
def test_env_check_rejects_incomplete_native_records(
    workspace_bundle: Path, tmp_path: Path, missing_field: str
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", ["bundle"])})),
        encoding="utf-8",
    )
    record = {
        "state": "READY",
        "verified": True,
        "converged": True,
        "version": "1.0",
        "installed_plugin_ids": ["bundle"],
        "components": {"bundles": ["bundle"]},
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

    report = json.loads(
        _run(
            workspace_bundle / "skills/env-check/scripts/env_check.py",
            "--json",
            "--native-evidence",
            str(native),
            env=env,
            cwd=tmp_path,
        ).stdout
    )

    assert report["status"] == "degraded"
    assert (
        f"missing required field: {missing_field}"
        in report["harnesses"]["omp"]["observed"]["validation_errors"]
    )


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    (
        ("state", "DRIFTED", "DRIFTED state cannot be converged"),
        ("state", "UNKNOWN", "state must be READY, DEGRADED, BLOCKED, or DRIFTED"),
        ("state", [], "state must be READY, DEGRADED, BLOCKED, or DRIFTED"),
        ("state", {}, "state must be READY, DEGRADED, BLOCKED, or DRIFTED"),
        ("state", "BLOCKED", "BLOCKED state flags are inconsistent"),
        (
            "capabilities",
            [],
            "capabilities must map non-empty strings to non-empty strings",
        ),
        ("components", [], "components must map non-empty strings to string lists"),
        ("warnings", "invalid", "warnings must be a list of strings"),
    ),
)
def test_env_check_rejects_malformed_native_records(
    workspace_bundle: Path,
    tmp_path: Path,
    field: str,
    value: object,
    expected_error: str,
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", ["bundle"])})),
        encoding="utf-8",
    )
    record = {
        "state": "READY",
        "verified": True,
        "converged": True,
        "version": "1.0",
        "installed_plugin_ids": ["bundle"],
        "capabilities": {},
        "components": {"bundles": ["bundle"]},
        "errors": [],
        "warnings": [],
    }
    record[field] = value
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {"operation": "reconcile", "harnesses": {"omp": record}, "errors": []}
        ),
        encoding="utf-8",
    )

    report = json.loads(
        _run(
            workspace_bundle / "skills/env-check/scripts/env_check.py",
            "--json",
            "--native-evidence",
            str(native),
            env=env,
            cwd=tmp_path,
        ).stdout
    )

    assert report["status"] == "degraded"
    assert expected_error in report["harnesses"]["omp"]["observed"]["validation_errors"]


def test_env_check_preserves_declared_degradation_when_converged(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", ["bundle"])})),
        encoding="utf-8",
    )
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {
                "operation": "reconcile",
                "harnesses": {
                    "omp": {
                        "state": "DEGRADED",
                        "verified": True,
                        "converged": True,
                        "version": "1.0",
                        "installed_plugin_ids": ["bundle"],
                        "components": {"bundles": ["bundle"]},
                        "capabilities": {},
                        "errors": ["declared degradation"],
                        "warnings": [],
                    }
                },
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    report = json.loads(
        _run(
            workspace_bundle / "skills/env-check/scripts/env_check.py",
            "--json",
            "--native-evidence",
            str(native),
            env=env,
            cwd=tmp_path,
        ).stdout
    )

    assert report["status"] == "ok"
    assert report["harnesses"]["omp"]["observed"]["converged"] is True
    assert report["harnesses"]["omp"]["observed"]["errors"] == ["declared degradation"]


def test_env_check_separates_receipt_from_native_observation(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _with_omp_fixture(_isolated_env(tmp_path), tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    receipt = state_root / "installation.json"
    receipt.write_text(
        json.dumps(
            _valid_receipt({"omp": _harness_receipt("omp", ["manifest-workspace"])})
        ),
        encoding="utf-8",
    )
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps(
            {
                "operation": "reconcile",
                "state": "READY",
                "errors": [],
                "harnesses": {
                    "omp": {
                        "state": "READY",
                        "verified": True,
                        "converged": True,
                        "version": "1.0",
                        "installed_plugin_ids": ["manifest-workspace"],
                        "components": {"bundles": ["manifest-workspace"]},
                        "capabilities": {},
                        "errors": [],
                        "warnings": [],
                    },
                    "optional-absent": {"state": "DRIFTED", "verified": False},
                },
            }
        ),
        encoding="utf-8",
    )
    script = workspace_bundle / "skills/env-check/scripts/env_check.py"

    result = _run(
        script, "--json", "--native-evidence", str(native), env=env, cwd=tmp_path
    )

    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["status"] == "ok"
    assert report["harnesses"]["omp"]["observed"]["version"] == "1.0"
    assert report["harnesses"]["omp"]["authentication"] == "not_tested"
    assert report["inventories"]["omp"]["selected"] is True
    assert report["native_observed"] is True
    assert list(state_root.iterdir()) == [receipt]


def test_env_check_missing_selected_native_is_degraded(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"claude": _harness_receipt("claude")})),
        encoding="utf-8",
    )
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps({"operation": "reconcile", "harnesses": {}, "errors": []}),
        encoding="utf-8",
    )
    script = workspace_bundle / "skills/env-check/scripts/env_check.py"

    result = _run(
        script, "--json", "--native-evidence", str(native), env=env, cwd=tmp_path
    )

    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert any("absent from native observation" in item for item in report["warnings"])


def test_env_check_reports_native_receipt_drift_and_ignores_unselected(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    state_root = Path(env["XDG_STATE_HOME"]) / "manifest"
    state_root.mkdir(parents=True)
    (state_root / "installation.json").write_text(
        json.dumps(_valid_receipt({"omp": _harness_receipt("omp", ["manifest-docs"])})),
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
                        "version": "2.0",
                        "installed_plugin_ids": [],
                        "components": {},
                        "capabilities": {},
                        "errors": [],
                        "warnings": [],
                    },
                    "cursor": {"state": "DRIFTED", "verified": False},
                },
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    script = workspace_bundle / "skills/env-check/scripts/env_check.py"

    result = _run(
        script, "--json", "--native-evidence", str(native), env=env, cwd=tmp_path
    )

    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["harnesses"]["omp"]["observed"]["version"] == "2.0"
    assert report["unselected_observed"] == ["cursor"]
    assert any("version differs" in warning for warning in report["warnings"])
    assert any("plugins not observed" in warning for warning in report["warnings"])


def test_env_check_malformed_receipt_is_non_success(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{", encoding="utf-8")

    result = _run(
        workspace_bundle / "skills/env-check/scripts/env_check.py",
        "--json",
        env=env,
        cwd=tmp_path,
    )

    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
