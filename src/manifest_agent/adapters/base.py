"""Stable harness adapter protocol and shared verification rules."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from manifest_agent.adapters.adapter_command_results import (
    _classified_diagnostic_result,
    _command_diagnostic,
    _unselected_optional_result,
)
from manifest_agent.adapters.capability_lifecycle import (
    CapabilityAdapterMixin as CapabilityAdapterMixin,
)
from manifest_agent.adapters.capability_lifecycle import (
    CapabilityPlan,
)
from manifest_agent.adapters.capability_lifecycle import (
    NativeMcpInventory as NativeMcpInventory,
)
from manifest_agent.adapters.capability_lifecycle import (
    normalize_native_mcp_inventory as normalize_native_mcp_inventory,
)
from manifest_agent.contracts import CompatibilityStatus, Component
from manifest_agent.models import (
    AdapterMutationHandle,
    BundleContract,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

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
class Detection:
    """Presence and version details for one native harness executable."""

    present: bool
    executable: str | None
    version: str | None
    reason: str | None = None


@runtime_checkable
class HarnessAdapter(Protocol):
    """The only harness-specific seam consumed by the coordinator service."""

    name: str

    def detect(self) -> Detection:
        """Report native harness availability without changing state."""
        ...

    def inspect(self, desired: DesiredState) -> HarnessResult:
        """Verify the effective native state against the desired release."""
        ...

    def install(self, desired: DesiredState) -> HarnessResult:
        """Converge one harness and return its truthful effective state."""
        ...

    def apply_capabilities(self, plan: CapabilityPlan) -> HarnessResult:
        """Apply the resolved cross-bundle capability union."""
        ...

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove only resources owned by the supplied receipt."""
        ...

    def prepare_reconcile(
        self, receipt: HarnessReceipt, prior: DesiredState, desired: DesiredState
    ) -> AdapterMutationHandle:
        """Prepare exact prior/target inventory authority without changing state."""
        ...

    def apply_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        """Apply a prepared release mutation."""
        ...

    def verify_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        """Verify a prepared release mutation."""
        ...

    def classify_reconcile_state(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> str:
        """Classify interrupted state as exact prior, target, or other."""
        ...

    def rollback_reconcile(
        self, handle: AdapterMutationHandle, prior: DesiredState
    ) -> HarnessResult:
        """Compensate a prepared release mutation to the prior release."""
        ...


def normalize_component_identity(bundle: str, kind: str, stable_id: str) -> str:
    """Return the canonical evidence identity for one contract surface."""
    if not bundle or not kind or not stable_id:
        raise ValueError("component identity fields must be non-empty")
    if any(":" in field for field in (bundle, kind, stable_id)):
        raise ValueError("component identity fields must not contain ':'")
    return f"{bundle}:{kind}:{stable_id}"


def native_command_result(
    harness: str,
    command: CommandResult,
    tier: CapabilityTier,
    *,
    selected: bool = False,
) -> HarnessResult:
    """Classify one native command without losing or leaking its diagnostics."""
    if tier is CapabilityTier.OPTIONAL and not selected:
        return _unselected_optional_result(harness)
    if command.returncode == 0:
        return HarnessResult(harness, ResultState.READY, (), {})

    return _classified_diagnostic_result(harness, tier, _command_diagnostic(command))


def run_native_command(
    harness: str,
    runner: CommandRunner,
    argv: Sequence[str],
    tier: CapabilityTier,
    *,
    selected: bool = False,
    env: Mapping[str, str] | None = None,
) -> HarnessResult:
    """Run and classify a native command without leaking execution exceptions."""
    if tier is CapabilityTier.OPTIONAL and not selected:
        return _unselected_optional_result(harness)
    try:
        command = runner.run(argv, env=env)
    except Exception as error:
        diagnostic = redact_text(
            f"native command execution failed ({type(error).__name__}): {error}"
        )
        return _classified_diagnostic_result(harness, tier, diagnostic)
    return native_command_result(harness, command, tier, selected=selected)


def verify_required_plugins(
    harness: str,
    desired: DesiredState,
    installed_plugin_ids: Collection[str],
) -> HarnessResult:
    """Require evidence that every desired domain bundle is installed."""
    installed = _evidence_set(installed_plugin_ids)
    required = tuple(contract.name for contract in desired.all_contracts)
    errors = tuple(
        f"missing required plugin: {plugin_id}"
        for plugin_id in required
        if plugin_id not in installed
    )
    verified = tuple(plugin_id for plugin_id in required if plugin_id in installed)
    return HarnessResult(
        harness=harness,
        state=ResultState.BLOCKED if errors else ResultState.READY,
        installed_plugin_ids=verified,
        capabilities={},
        errors=errors,
    )


def verify_declared_components(
    harness: str,
    desired: DesiredState,
    evidence: Collection[str] | Mapping[str, object],
) -> HarnessResult:
    """Verify every applicable contract surface from explicit adapter evidence."""
    observed = _evidence_set(evidence)
    results = tuple(
        _verify_contract(harness, desired, contract, observed)
        for contract in desired.all_contracts
    )
    if not results:
        return HarnessResult(harness, ResultState.READY, (), {})
    return combine_results(*results)


def collect_native_component_evidence(
    desired: DesiredState,
    plugin_roots: Mapping[str, Path],
    native_mcp_servers: Mapping[str, Collection[str]],
    which: Callable[[str], str | None],
) -> set[str]:
    """Collect file and native capability evidence without assuming exposure."""
    evidence: set[str] = set()
    for contract in desired.all_contracts:
        root = plugin_roots.get(contract.name)
        if root is not None:
            _add_installed_file_evidence(evidence, desired, contract, root)
        evidence.update(
            normalize_component_identity(contract.name, "mcp", server)
            for server in native_mcp_servers.get(contract.name, ())
        )
        for tier in CapabilityTier:
            evidence.update(
                normalize_component_identity(contract.name, "executable", executable)
                for executable in contract.capabilities.executables[tier]
                if which(executable) is not None
            )
    return evidence


def _add_installed_file_evidence(
    evidence: set[str],
    desired: DesiredState,
    contract: BundleContract,
    root: Path,
) -> None:
    desired_skills = (
        desired.bundle_path(contract.name) / contract.components.skills_root
    )
    installed_skills = root / contract.components.skills_root
    for pattern in contract.components.skills_include:
        for path in desired_skills.glob(pattern):
            if (
                path.is_file()
                and (installed_skills / path.relative_to(desired_skills)).is_file()
            ):
                evidence.add(
                    normalize_component_identity(
                        contract.name, "skill", path.parent.name
                    )
                )
    for kind, attribute in _COMPONENT_GROUPS:
        for component in getattr(contract.components, attribute):
            if (root / component.path).is_file():
                evidence.add(
                    normalize_component_identity(contract.name, kind, component.id)
                )


def _verify_contract(
    harness: str,
    desired: DesiredState,
    contract: BundleContract,
    observed: set[str],
) -> HarnessResult:
    bundle_status = contract.compatibility[harness]
    bundle_identities = _contract_identities(harness, desired, contract)
    if bundle_status.mode == "unsupported":
        return _unsupported_bundle_result(
            harness, desired, bundle_status, bundle_identities
        )
    if bundle_status.mode in _DEGRADED_MODES:
        return _degraded_bundle_result(
            harness, desired, bundle_status, bundle_identities
        )

    result = _ContractVerification({}, [], [], ResultState.READY)
    for identity, tier, component_status in bundle_identities:
        _verify_contract_identity(
            desired,
            identity,
            tier,
            component_status or bundle_status,
            observed,
            result,
        )

    return HarnessResult(
        harness=harness,
        state=result.state,
        installed_plugin_ids=(),
        capabilities=result.capabilities,
        errors=tuple(result.errors),
        warnings=tuple(result.warnings),
    )


@dataclass
class _ContractVerification:
    capabilities: dict[str, str]
    errors: list[str]
    warnings: list[str]
    state: ResultState


def _verify_contract_identity(
    desired: DesiredState,
    identity: str,
    tier: CapabilityTier,
    status: CompatibilityStatus,
    observed: set[str],
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
        result.capabilities[identity] = status.mode
        result.state = _higher_state(result.state, ResultState.DEGRADED)
        _append_once(result.errors, _compatibility_reason(status))
        return
    if status.mode not in _MODE_STATES:
        raise ValueError(f"unknown compatibility mode {status.mode!r} for {identity}")
    if tier is CapabilityTier.OPTIONAL and not _optional_selected(desired, identity):
        return
    if identity in observed:
        result.capabilities[identity] = "verified"
        return
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
    desired: DesiredState,
    status: CompatibilityStatus,
    identities: tuple[tuple[str, CapabilityTier, CompatibilityStatus | None], ...],
) -> HarnessResult:
    capabilities = {
        identity: status.mode
        for identity, tier, _component_status in identities
        if tier is not CapabilityTier.OPTIONAL or _optional_selected(desired, identity)
    }
    return HarnessResult(
        harness,
        ResultState.DEGRADED,
        (),
        capabilities,
        errors=(_compatibility_reason(status),),
    )


def _unsupported_bundle_result(
    harness: str,
    desired: DesiredState,
    status: CompatibilityStatus,
    identities: tuple[tuple[str, CapabilityTier, CompatibilityStatus | None], ...],
) -> HarnessResult:
    capabilities = {
        identity: status.mode
        for identity, tier, _component_status in identities
        if tier is not CapabilityTier.OPTIONAL or _optional_selected(desired, identity)
    }
    return HarnessResult(
        harness,
        ResultState.BLOCKED,
        (),
        capabilities,
        errors=(_compatibility_reason(status),),
    )


def combine_results(*results: HarnessResult) -> HarnessResult:
    """Combine adapter steps while preserving every reported diagnostic."""
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
    capabilities = {
        identity: status
        for result in results
        for identity, status in result.capabilities.items()
    }
    return HarnessResult(
        harness=harness,
        state=state,
        installed_plugin_ids=plugins,
        capabilities=capabilities,
        errors=tuple(error for result in results for error in result.errors),
        warnings=tuple(warning for result in results for warning in result.warnings),
        owned_entries=tuple(
            dict.fromkeys(entry for result in results for entry in result.owned_entries)
        ),
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
    for skill_path in sorted(skill_paths):
        identities.append(
            (
                normalize_component_identity(bundle, "skill", skill_path.parent.name),
                CapabilityTier.REQUIRED,
                None,
            )
        )
    for kind, attribute in _COMPONENT_GROUPS:
        for component in getattr(contract.components, attribute):
            identities.append(
                (
                    normalize_component_identity(bundle, kind, component.id),
                    CapabilityTier.REQUIRED,
                    _component_status(component, harness),
                )
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


def _evidence_set(
    evidence: Collection[str] | Mapping[str, object],
) -> set[str]:
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
