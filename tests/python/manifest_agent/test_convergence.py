"""A harness may converge with contract-declared degradation, but not with gaps.

`bootstrap_sync` aborted unless a harness reached exactly READY. Codex can never
reach READY: manifest-ops declares two hooks permanently `degraded` for it
(Codex's whole native event surface is PermissionRequest/SessionStart/Stop, with
no post-write event for version-pin's `PostToolUse` matcher). So the contract
declares a permanent, expected degradation and the gate demanded perfection —
codex could not converge by construction.

Accepting DEGRADED wholesale would be worse than the bug: DEGRADED is ALSO the
state set by `missing default capability evidence`, so a genuinely absent
default capability would sail through the gate that exists to catch it. These
tests pin the distinction — declared degradation converges, missing evidence
does not.
"""

import pytest

from manifest_agent.adapters.convergence import has_undeclared_degradation
from manifest_agent.bootstrap_sync import _converged
from manifest_agent.models import HarnessResult, ResultState


def _result(
    state: ResultState,
    capabilities: dict[str, str],
    errors=(),
    declared_degradations=(),
) -> HarnessResult:
    return HarnessResult(
        "codex",
        state,
        (),
        capabilities,
        tuple(errors),
        declared_degradations=tuple(declared_degradations),
    )


def test_declared_degradation_alone_is_convergent() -> None:
    errors = (
        "Codex exposes the on-demand version-pin skill but has no native "
        "file-save hook surface.",
    )
    result = _result(
        ResultState.DEGRADED,
        {"manifest-ops:hook:version-pin": "degraded"},
        errors,
        errors,
    )

    assert has_undeclared_degradation(result) is False


def test_missing_default_capability_evidence_is_not_convergent() -> None:
    """The regression this gate must keep catching: an absent default capability."""
    result = _result(
        ResultState.DEGRADED,
        {"manifest-workspace:mcp:context7": "missing"},
        ("default MCP evidence could not be verified",),
    )

    assert has_undeclared_degradation(result) is True


def test_declared_degradation_plus_missing_evidence_is_not_convergent() -> None:
    """A real gap must not be laundered by an unrelated declared degradation."""
    declared = (
        "Codex exposes the on-demand version-pin skill but has no native "
        "file-save hook surface.",
    )
    result = _result(
        ResultState.DEGRADED,
        {
            "manifest-ops:hook:version-pin": "degraded",
            "manifest-workspace:mcp:context7": "missing",
        },
        (*declared, "default MCP evidence could not be verified"),
        declared,
    )

    assert has_undeclared_degradation(result) is True


def test_ready_result_has_no_degradation() -> None:
    result = _result(ResultState.READY, {"manifest-ops:hook:version-pin": "verified"})

    assert has_undeclared_degradation(result) is False


@pytest.mark.parametrize(
    "status",
    [
        "missing",
        "failed",
        "disabled",
        "conflicting",
        "unknown-transport",
        "observation-unavailable",
    ],
)
def test_non_contract_degradation_status_never_converges(status: str) -> None:
    result = _result(
        ResultState.DEGRADED,
        {"manifest-workspace:mcp:context7": status},
        ("inventory did not verify the declared capability",),
    )

    assert _converged(result) is False


def test_unselected_optional_missing_does_not_block_convergence() -> None:
    """An unselected optional capability is recorded `missing` but warns only."""
    errors = (
        "Codex exposes the on-demand version-pin skill but has no native "
        "file-save hook surface.",
    )
    result = _result(
        ResultState.DEGRADED,
        {
            "manifest-ops:hook:version-pin": "degraded",
            "manifest-security:mcp:semgrep": "missing",
        },
        errors,
        errors,
    )

    assert has_undeclared_degradation(result) is False
