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


@pytest.mark.parametrize(
    "entrypoint",
    [
        "env-check/scripts/env_check.py",
        "deploy-reconcile/scripts/plugin_reconcile.py",
    ],
)
@pytest.mark.parametrize(
    "case",
    [
        "active",
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
    active = _harness_receipt("claude", ["manifest-workspace@manifest"])
    retired = _harness_receipt("gemini")
    records = {"claude": active}
    if case != "active":
        records["gemini"] = retired
    if case == "retired-only":
        records.pop("claude")
    elif case == "retired-identity":
        retired["harness"] = "old-name"
    elif case == "retired-unverified":
        retired.update(verified=False, capabilities={"old": "ready"}, errors=[])
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
    receipt = tmp_path / "explicit.json"
    receipt.write_text(json.dumps(_valid_receipt(copy.deepcopy(records))))
    before = receipt.read_bytes()
    try:
        decoded = read_receipt(receipt)
    except StateError:
        decoded = None
    evidence = _write_native_evidence(tmp_path, active)
    env = _isolated_env(tmp_path)
    result = _run(
        SCRIPTS / entrypoint,
        "--json",
        "--receipt",
        str(receipt),
        "--native-evidence",
        str(evidence),
        env=env,
        cwd=tmp_path,
    )
    assert result.stdout, result.stderr
    report = json.loads(result.stdout)
    expected = _assert_decoded_harnesses(report, decoded)
    assert "gemini" not in report["harnesses"]
    if entrypoint.startswith("env-check/"):
        assert report["receipt"]["valid"] is bool(
            decoded is not None and decoded.harnesses
        )
        assert report["receipt"]["selected"] == expected
        problems = report["warnings"]
    else:
        assert report["receipt"] == str(receipt)
        problems = [item["reason"] for item in report["drift"]]
        assert any("coordinator schema" in item for item in problems) is (
            decoded is None
        )
    if case == "retired-only":
        assert "installation receipt selects no harness" in problems
    assert receipt.read_bytes() == before


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
