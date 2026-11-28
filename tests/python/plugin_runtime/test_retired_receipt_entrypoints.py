"""Public consumers decode retired records exactly as the coordinator does."""

import copy
import json
from pathlib import Path

import pytest

from manifest_agent.state import StateError, read_receipt
from tests.python.plugin_runtime.workspace_runtime_helpers import (
    _harness_receipt,
    _isolated_env,
    _run,
    _valid_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins/manifest-workspace/skills"


# Receipt-bound consumers take saved reconcile evidence; the portable
# deploy-reconcile path takes typed inspection evidence instead.
ENTRYPOINTS = {
    "env-check": ("env-check/scripts/env_check.py", "--native-evidence"),
    "deploy-reconcile": (
        "deploy-reconcile/scripts/plugin_reconcile.py",
        "--native-evidence",
    ),
    "deploy-reconcile-portable": (
        "deploy-reconcile/scripts/plugin_reconcile.py",
        "--native-inspection",
    ),
}


@pytest.mark.parametrize("entrypoint", sorted(ENTRYPOINTS))
@pytest.mark.parametrize(
    "case",
    [
        "active",
        "active-unverified",
        "retired",
        "retired-only",
        "retired-identity",
        "retired-unverified",
        "unknown",
        "bad-list",
        "bad-map",
        "bad-owned-entry",
        "extra-field",
    ],
)
def test_both_public_receipt_consumers_match_state_decoder(tmp_path, entrypoint, case):
    active, records = _case_records(case)
    receipt = tmp_path / "explicit.json"
    receipt.write_text(json.dumps(_valid_receipt(copy.deepcopy(records))))
    before = receipt.read_bytes()
    try:
        decoded = read_receipt(receipt)
    except StateError:
        decoded = None
    evidence = _write_native_evidence(tmp_path, active)
    env = _isolated_env(tmp_path)
    script, evidence_flag = ENTRYPOINTS[entrypoint]
    result = _run(
        SCRIPTS / script,
        "--json",
        "--receipt",
        str(receipt),
        evidence_flag,
        str(evidence),
        env=env,
        cwd=tmp_path,
    )
    assert result.stdout, result.stderr
    report = json.loads(result.stdout)
    expected = _assert_decoded_harnesses(report, decoded)
    assert "gemini" not in report["harnesses"]
    problems = _consumer_problems(report, entrypoint, receipt, decoded, expected)
    if case == "retired-only":
        empty = (
            "receipt records no harnesses"
            if entrypoint == "deploy-reconcile-portable"
            else "installation receipt selects no harness"
        )
        assert empty in problems
    assert receipt.read_bytes() == before


@pytest.mark.parametrize("contents", ["null", "[]"], ids=["null", "array"])
def test_portable_reconcile_rejects_non_object_receipt_with_harness(tmp_path, contents):
    receipt = tmp_path / "explicit.json"
    receipt.write_text(contents)
    with pytest.raises(StateError):
        read_receipt(receipt)

    active = _harness_receipt("claude", ["manifest-workspace@manifest"])
    evidence = _write_native_evidence(tmp_path, active)
    script, evidence_flag = ENTRYPOINTS["deploy-reconcile-portable"]
    result = _run(
        SCRIPTS / script,
        "--json",
        "--receipt",
        str(receipt),
        "--harness",
        "claude",
        evidence_flag,
        str(evidence),
        env=_isolated_env(tmp_path),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["verified"] is False
    assert any("coordinator schema" in item["reason"] for item in report["drift"])
    assert any("coordinator schema" in item["reason"] for item in report["unverified"])


def _case_records(case):
    active = _harness_receipt("claude", ["manifest-workspace@manifest"])
    retired = _harness_receipt("gemini")
    records = {"claude": active}
    if case not in {"active", "active-unverified"}:
        records["gemini"] = retired
    if case == "retired-only":
        records.pop("claude")
    elif case == "retired-identity":
        retired["harness"] = "old-name"
    elif case == "retired-unverified":
        retired.update(verified=False, capabilities={"old": "ready"}, errors=[])
    elif case == "active-unverified":
        active.update(verified=False, errors=[])
    elif case == "unknown":
        records["unknown"] = records.pop("gemini")
    elif case == "bad-list":
        retired["plugin_ids"] = "not-a-list"
    elif case == "bad-map":
        retired["capabilities"] = {"old": False}
    elif case == "bad-owned-entry":
        retired["owned_entries"] = [{"kind": "owned-file"}]
    elif case == "extra-field":
        retired["unexpected"] = "value"
    return active, records


def _consumer_problems(report, entrypoint, receipt, decoded, expected):
    if entrypoint == "env-check":
        assert report["receipt"]["valid"] is bool(
            decoded is not None and decoded.harnesses
        )
        assert report["receipt"]["selected"] == expected
        return report["warnings"]
    assert report["receipt"] == str(receipt)
    problems = [item["reason"] for item in report["drift"]]
    problems += [item["reason"] for item in report["unverified"]]
    assert any("coordinator schema" in item for item in problems) is (decoded is None)
    if decoded is None:
        assert report["status"] in {"degraded", "unverified"}
        assert report["verified"] is False
    return problems


def _assert_decoded_harnesses(report, decoded):
    expected = sorted(decoded.harnesses) if decoded else []
    assert sorted(report["harnesses"]) == expected
    return expected


def _write_native_evidence(tmp_path, active):
    evidence = tmp_path / "native.json"
    evidence.write_text(
        json.dumps(
            {
                "operation": "reconcile",
                "state": "READY",
                "errors": [],
                "harnesses": {
                    "claude": {
                        "state": "READY",
                        "verified": True,
                        "converged": True,
                        "version": "1.0",
                        "installed_plugin_ids": active["plugin_ids"],
                        "capabilities": {},
                        "components": {},
                        "errors": [],
                        "warnings": [],
                    }
                },
            }
        )
    )
    return evidence
