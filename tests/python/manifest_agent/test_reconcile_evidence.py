"""`reconcile --json` per-harness evidence: native version, truthful `verified`,
and bundle-grouped `components`, consumed by ``render_plugin_capability_matrix.py``.

A harness that never populated these fields left the matrix tool's inspection
contract permanently unsatisfiable from live evidence: ``version`` and
``verified`` were absent, and ``components`` was always empty even when the
harness genuinely installed and verified plugin components.
"""

from __future__ import annotations

import pytest

from manifest_agent.models import HarnessResult, ResultState
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    FakeDetection,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path):
    return make_service_factory(tmp_path)


def _claude_result() -> HarnessResult:
    return HarnessResult(
        "claude",
        ResultState.READY,
        ("manifest-code-quality",),
        {
            "manifest-code-quality:skill:ai-code-audit": "verified",
            "manifest-code-quality:executable:git": "verified",
            "executable:git": "verified",
            "manifest-code-quality:mcp:context7": "missing",
        },
    )


def test_reconcile_json_carries_the_probed_native_version_and_truthful_verified(
    service_factory,
):
    """A READY reconcile against a present, working CLI must report the exact
    native version the adapter's own `detect()` probed -- never a placeholder
    -- and `verified: True` because the state genuinely converged."""
    claude = FakeAdapter("claude", _claude_result())
    claude.detection = FakeDetection(True, "claude", "2.1.267", None)
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()

    report = service.reconcile(apply=False)
    record = report.to_dict()["harnesses"]["claude"]

    assert record["version"] == "2.1.267"
    assert record["verified"] is True


def test_reconcile_json_components_group_verified_evidence_by_bundle(
    service_factory,
):
    """`components` must map each installed bundle to its verified contract
    surfaces (skill/agent/hook/runtime/guidance kinds) so the matrix tool can
    join evidence per bundle. Evidence that is not truthfully verified (e.g.
    `missing`) must never appear, and executable/mcp identities are capability
    evidence, not component evidence."""
    claude = FakeAdapter("claude", _claude_result())
    claude.detection = FakeDetection(True, "claude", "2.1.267", None)
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()

    report = service.reconcile(apply=False)
    record = report.to_dict()["harnesses"]["claude"]

    assert record["components"]["manifest-code-quality"] == ["skill:ai-code-audit"]
    assert "mcp:context7" not in record["components"]["manifest-code-quality"]
    assert "executable:git" not in record["components"]["manifest-code-quality"]


def test_reconcile_json_absent_cli_reports_blocked_without_a_fabricated_version(
    service_factory,
):
    """A harness whose native CLI has gone missing since install must report
    an honest BLOCKED record: no invented version, no false verification, and
    no components claimed for a CLI Manifest could not even reach."""
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"codex": codex}, harnesses=("codex",))
    service.install()
    service.harnesses = ()
    codex.detection.present = False
    codex.detection.executable = None
    codex.detection.version = None
    codex.detection.reason = "codex CLI not present"

    report = service.reconcile(apply=False)
    record = report.to_dict()["harnesses"]["codex"]

    assert record["state"] == "BLOCKED"
    assert record["version"] is None
    assert record["verified"] is False
    assert record["components"] == {}
