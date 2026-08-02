"""Partial harness results preserve verified, unrelated ownership."""

from __future__ import annotations

from manifest_agent.models import ResultState
from manifest_agent.state import read_receipt
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


def test_failed_harness_does_not_roll_back_verified_unrelated_harness(tmp_path) -> None:
    service = make_service_factory(tmp_path)(
        {
            "claude": FakeAdapter("claude", harness_result("claude")),
            "codex": FakeAdapter(
                "codex", harness_result("codex", ResultState.BLOCKED, errors=("fixture failure",))
            ),
        }
    )

    result = service.install()
    receipt = read_receipt(service.receipt_path)

    assert result.state is ResultState.BLOCKED
    assert receipt is not None
    assert receipt.harnesses["claude"].verified is True
    assert receipt.harnesses["codex"].verified is False


def test_reconcile_apply_repairs_only_drifted_harness(tmp_path) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = make_service_factory(tmp_path)({"claude": claude, "codex": codex})
    service.install()
    claude.calls.clear()
    codex.calls.clear()
    codex.inspection = harness_result("codex", ResultState.DRIFTED)

    service.reconcile(apply=True)

    assert claude.calls == ["detect", "inspect"]
    assert codex.calls == ["detect", "inspect", "install", "inspect"]
