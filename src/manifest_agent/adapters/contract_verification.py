"""Contract component verification with explicit evidence-failure provenance."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from manifest_agent.contracts import CompatibilityStatus, Component
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    DesiredState,
    HarnessResult,
    ResultState,
)

_COMPONENT_GROUPS = (
    ("agent", "agents"),
    ("hook", "hooks"),
    ("runtime", "runtime"),
    ("guidance", "guidance"),
)
_MODE_STATES = frozenset({"native", "generated", "imported"})
_DEGRADED_MODES = frozenset({"degraded"})
_STATE_PRIORITY = {
    ResultState.READY: 0,
    ResultState.DEGRADED: 1,
    ResultState.DRIFTED: 2,
    ResultState.BLOCKED: 3,
}


@dataclass(frozen=True)
class CapabilityEvidenceFailure:
    """A typed reason an adapter could not verify one capability identity."""

    status: str
    diagnostic: str

    def __post_init__(self) -> None:
        if not self.status or not self.diagnostic:
            raise ValueError(
                "capability evidence failures require status and diagnostic"
            )


@dataclass(frozen=True)
class _EvidenceContext:
    desired: DesiredState
    observed: set[str]
    failures: Mapping[str, CapabilityEvidenceFailure]


@dataclass
class _ContractVerification:
    capabilities: dict[str, str]
    errors: list[str]
    warnings: list[str]
    declared_degradations: list[str]
    state: ResultState


def normalize_component_identity(bundle: str, kind: str, stable_id: str) -> str:
    """Return the canonical evidence identity for one contract surface."""
    if not bundle or not kind or not stable_id:
        raise ValueError("component identity fields must be non-empty")
    if any(":" in field for field in (bundle, kind, stable_id)):
        raise ValueError("component identity fields must not contain ':'")
    return f"{bundle}:{kind}:{stable_id}"


def verify_declared_components(
    harness: str,
    desired: DesiredState,
    evidence: Collection[str] | Mapping[str, object],
    failures: Mapping[str, CapabilityEvidenceFailure] | None = None,
) -> HarnessResult:
    """Verify every applicable contract surface from explicit adapter evidence."""
    context = _EvidenceContext(desired, _evidence_set(evidence), failures or {})
    results = tuple(
        _verify_contract(harness, contract, context)
        for contract in desired.all_contracts
    )
    if not results:
        return HarnessResult(harness, ResultState.READY, (), {})
    return combine_results(*results)


def combine_results(*results: HarnessResult) -> HarnessResult:
    """Combine adapter steps while preserving diagnostics and their provenance."""
    if not results:
        raise ValueError("at least one harness result is required")
    harness = results[0].harness
    if any(result.harness != harness for result in results):
        raise ValueError("cannot combine results from different harnesses")
    state = max((result.state for result in results), key=_STATE_PRIORITY.__getitem__)
    plugins = tuple(
        dict.fromkeys(
            plugin for result in results for plugin in result.installed_plugin_ids
        )
    )
    return HarnessResult(
        harness=harness,
        state=state,
        installed_plugin_ids=plugins,
        capabilities={
            identity: status
            for result in results
            for identity, status in result.capabilities.items()
        },
        errors=tuple(error for result in results for error in result.errors),
        warnings=tuple(warning for result in results for warning in result.warnings),
        owned_entries=tuple(
            dict.fromkeys(entry for result in results for entry in result.owned_entries)
        ),
        declared_degradations=tuple(
            diagnostic
            for result in results
            for diagnostic in result.declared_degradations
        ),
    )


def _verify_contract(
    harness: str, contract: BundleContract, context: _EvidenceContext
) -> HarnessResult:
    bundle_status = contract.compatibility[harness]
    identities = _contract_identities(harness, context.desired, contract)
    if bundle_status.mode == "unsupported":
        return _unsupported_bundle_result(harness, bundle_status, identities, context)
    if bundle_status.mode in _DEGRADED_MODES:
        return _degraded_bundle_result(harness, bundle_status, identities, context)
    result = _ContractVerification({}, [], [], [], ResultState.READY)
    for identity, tier, component_status in identities:
        _verify_contract_identity(
            identity, tier, component_status or bundle_status, context, result
        )
    return HarnessResult(
        harness=harness,
        state=result.state,
        installed_plugin_ids=(),
        capabilities=result.capabilities,
        errors=tuple(result.errors),
        warnings=tuple(result.warnings),
        declared_degradations=tuple(result.declared_degradations),
    )


def _verify_contract_identity(
    identity: str,
    tier: CapabilityTier,
    status: CompatibilityStatus,
    context: _EvidenceContext,
    result: _ContractVerification,
) -> None:
    if status.mode == "not_applicable":
        return
    if status.mode == "unsupported":
        result.capabilities[identity] = status.mode
        result.state = ResultState.BLOCKED
        _append_once(result.errors, _compatibility_reason(status))
        return
    if status.mode in _DEGRADED_MODES:
        reason = _compatibility_reason(status)
        result.capabilities[identity] = status.mode
        result.state = _higher_state(result.state, ResultState.DEGRADED)
        _append_once(result.errors, reason)
        _append_once(result.declared_degradations, reason)
        return
    if status.mode not in _MODE_STATES:
        raise ValueError(f"unknown compatibility mode {status.mode!r} for {identity}")
    if tier is CapabilityTier.OPTIONAL and not _optional_selected(
        context.desired, identity
    ):
        return
    if identity in context.observed:
        result.capabilities[identity] = "verified"
        return
    failure = context.failures.get(identity)
    if failure is not None:
        _record_evidence_failure(identity, tier, failure, result)
        return
    _record_missing_evidence(identity, tier, result)


def _record_evidence_failure(
    identity: str,
    tier: CapabilityTier,
    failure: CapabilityEvidenceFailure,
    result: _ContractVerification,
) -> None:
    result.capabilities[identity] = failure.status
    if tier is CapabilityTier.REQUIRED:
        result.state = ResultState.BLOCKED
        result.errors.append(failure.diagnostic)
    elif tier is CapabilityTier.DEFAULT:
        result.state = _higher_state(result.state, ResultState.DEGRADED)
        result.errors.append(failure.diagnostic)
    else:
        result.warnings.append(failure.diagnostic)


def _record_missing_evidence(
    identity: str, tier: CapabilityTier, result: _ContractVerification
) -> None:
    result.capabilities[identity] = "missing"
    if tier is CapabilityTier.DEFAULT:
        result.state = _higher_state(result.state, ResultState.DEGRADED)
        result.errors.append(f"missing default capability evidence: {identity}")
    elif tier is CapabilityTier.OPTIONAL:
        result.warnings.append(
            f"missing selected optional capability evidence: {identity}"
        )
    else:
        result.state = ResultState.BLOCKED
        result.errors.append(f"missing adapter evidence: {identity}")


def _degraded_bundle_result(
    harness: str,
    status: CompatibilityStatus,
    identities: tuple[tuple[str, CapabilityTier, CompatibilityStatus | None], ...],
    context: _EvidenceContext,
) -> HarnessResult:
    reason = _compatibility_reason(status)
    capabilities = {
        identity: status.mode
        for identity, tier, _component_status in identities
        if tier is not CapabilityTier.OPTIONAL
        or _optional_selected(context.desired, identity)
    }
    return HarnessResult(
        harness,
        ResultState.DEGRADED,
        (),
        capabilities,
        errors=(reason,),
        declared_degradations=(reason,),
    )


def _unsupported_bundle_result(
    harness: str,
    status: CompatibilityStatus,
    identities: tuple[tuple[str, CapabilityTier, CompatibilityStatus | None], ...],
    context: _EvidenceContext,
) -> HarnessResult:
    capabilities = {
        identity: status.mode
        for identity, tier, _component_status in identities
        if tier is not CapabilityTier.OPTIONAL
        or _optional_selected(context.desired, identity)
    }
    return HarnessResult(
        harness,
        ResultState.BLOCKED,
        (),
        capabilities,
        errors=(_compatibility_reason(status),),
    )


def _contract_identities(
    harness: str, desired: DesiredState, contract: BundleContract
) -> tuple[tuple[str, CapabilityTier, CompatibilityStatus | None], ...]:
    bundle = contract.name
    identities: list[tuple[str, CapabilityTier, CompatibilityStatus | None]] = []
    skills_root = desired.bundle_path(bundle) / contract.components.skills_root
    skill_paths = {
        path
        for pattern in contract.components.skills_include
        for path in skills_root.glob(pattern)
        if path.is_file()
    }
    identities.extend(
        (
            normalize_component_identity(bundle, "skill", path.parent.name),
            CapabilityTier.REQUIRED,
            None,
        )
        for path in sorted(skill_paths)
    )
    for kind, attribute in _COMPONENT_GROUPS:
        identities.extend(
            (
                normalize_component_identity(bundle, kind, component.id),
                CapabilityTier.REQUIRED,
                _component_status(component, harness),
            )
            for component in getattr(contract.components, attribute)
        )
    for kind, tier_map in (
        ("mcp", contract.capabilities.mcp),
        ("executable", contract.capabilities.executables),
    ):
        for tier in CapabilityTier:
            identities.extend(
                (normalize_component_identity(bundle, kind, item), tier, None)
                for item in tier_map[tier]
            )
    return tuple(identities)


def _component_status(component: Component, harness: str) -> CompatibilityStatus | None:
    if component.compatibility is None:
        return None
    return component.compatibility.get(harness)


def _evidence_set(evidence: Collection[str] | Mapping[str, object]) -> set[str]:
    if isinstance(evidence, str):
        raise TypeError("adapter evidence must be a collection of identities")
    values = evidence.keys() if isinstance(evidence, Mapping) else evidence
    if any(not isinstance(value, str) for value in values):
        raise TypeError("adapter evidence identities must be strings")
    return set(values)


def _optional_selected(desired: DesiredState, identity: str) -> bool:
    _bundle, kind, stable_id = identity.split(":", 2)
    return bool(
        {identity, stable_id, f"{kind}:{stable_id}"} & desired.selected_optional
    )


def _compatibility_reason(status: CompatibilityStatus) -> str:
    if status.reason is None:
        raise ValueError(f"compatibility mode {status.mode!r} requires a reason")
    return status.reason


def _higher_state(left: ResultState, right: ResultState) -> ResultState:
    return max((left, right), key=_STATE_PRIORITY.__getitem__)


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
