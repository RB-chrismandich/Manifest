"""Coordinator report contracts for native OMP evidence."""

from __future__ import annotations

import pytest

from manifest_agent.models import HarnessResult, NativeInspection, ResultState
from manifest_agent.service_state import ServiceReport


@pytest.mark.parametrize("native", [None, NativeInspection("omp", "user", None)])
def test_absent_native_evidence_is_not_serialized_as_convergence(native):
    result = HarnessResult(
        "omp",
        ResultState.READY,
        (),
        {"package-lifecycle": "verified"},
        native_inspection=native,
    )
    document = ServiceReport("inspect", ResultState.READY, {"omp": result}).to_dict()
    assert document["state"] == "DEGRADED"
    assert document["harnesses"]["omp"]["state"] == "DEGRADED"
    assert document["harnesses"]["omp"]["converged"] is False
    assert document["harnesses"]["omp"]["verified"] is False


def test_native_evidence_requirement_does_not_change_other_harness_reports():
    result = HarnessResult("claude", ResultState.READY, (), {})
    document = ServiceReport("inspect", ResultState.READY, {"claude": result}).to_dict()
    assert document["state"] == "READY"
    assert document["harnesses"]["claude"]["state"] == "READY"
    assert document["harnesses"]["claude"]["converged"] is True
    assert document["harnesses"]["claude"]["verified"] is True
