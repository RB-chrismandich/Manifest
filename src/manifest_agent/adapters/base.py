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
from manifest_agent.adapters.component_presence import component_is_installed
from manifest_agent.adapters.contract_verification import (
    CapabilityEvidenceFailure as CapabilityEvidenceFailure,
)
from manifest_agent.adapters.contract_verification import (
    combine_results as combine_results,
)
from manifest_agent.adapters.contract_verification import (
    normalize_component_identity as normalize_component_identity,
)
from manifest_agent.adapters.contract_verification import (
    verify_declared_components as verify_declared_components,
)
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
            if component_is_installed(root / component.path):
                evidence.add(
                    normalize_component_identity(contract.name, kind, component.id)
                )


def _evidence_set(
    evidence: Collection[str] | Mapping[str, object],
) -> set[str]:
    if isinstance(evidence, str):
        raise TypeError("adapter evidence must be a collection of identities")
    values = evidence.keys() if isinstance(evidence, Mapping) else evidence
    if any(not isinstance(value, str) for value in values):
        raise TypeError("adapter evidence identities must be strings")
    return set(values)
