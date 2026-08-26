"""Contract tests for the shared harness adapter boundary and fixture CLI."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters import (
    AdapterRegistry,
    Detection,
    combine_results,
    native_command_result,
    verify_declared_components,
    verify_required_plugins,
)
from manifest_agent.contracts import (
    Capabilities,
    CompatibilityStatus,
    Component,
    Components,
    Provenance,
)
from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    BundleContract,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    MarketplaceSource,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.process import CommandRunner


class QueueRunner:
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    def queue(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.results.append(
            CommandResult(("fake", "native"), returncode, stdout, stderr)
        )

    def run(self, argv: Sequence[str]) -> CommandResult:
        assert tuple(argv) == ("fake", "native")
        return self.results.pop(0)


class RaisingRunner(CommandRunner):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        del env
        self.calls.append(tuple(argv))
        raise self.error


class FakeAdapter:
    name = "claude"
    adapter_version = "1"

    def __init__(self, evidence: set[str]) -> None:
        self.runner = QueueRunner()
        self.evidence = evidence

    def detect(self) -> Detection:
        return Detection(True, "fake", "1.0")

    def inspect(self, desired: DesiredState) -> HarnessResult:
        return verify_declared_components(self.name, desired, self.evidence)

    def install(self, desired: DesiredState) -> HarnessResult:
        command = self.runner.run(("fake", "native"))
        return native_command_result(self.name, command, CapabilityTier.REQUIRED)

    def apply_capabilities(self, plan) -> HarnessResult:
        del plan
        return HarnessResult(self.name, ResultState.READY, (), {})

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        del receipt
        return HarnessResult(self.name, ResultState.READY, (), {})

    def prepare_reconcile(
        self, receipt: HarnessReceipt, prior: DesiredState, desired: DesiredState
    ) -> AdapterMutationHandle:
        del receipt

        return AdapterMutationHandle(
            1,
            self.name,
            self.adapter_version,
            "0" * 64,
            tuple(
                AdapterPluginState(contract.name, contract.version, True)
                for contract in prior.all_contracts
            ),
            tuple(
                AdapterPluginState(contract.name, contract.version, True)
                for contract in desired.all_contracts
            ),
        )

    def apply_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        del handle, desired
        return HarnessResult(self.name, ResultState.READY, (), {})

    def verify_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        del handle
        return self.inspect(desired)

    def classify_reconcile_state(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> str:
        del handle, desired
        return "target"

    def rollback_reconcile(
        self, handle: AdapterMutationHandle, prior: DesiredState
    ) -> HarnessResult:
        del handle, prior
        return HarnessResult(self.name, ResultState.READY, (), {})


@pytest.fixture
def desired(tmp_path: Path) -> DesiredState:
    skills = tmp_path / "plugins" / "manifest-workspace" / "skills"
    (skills / "help").mkdir(parents=True)
    (skills / "help" / "SKILL.md").write_text("# Help\n", encoding="utf-8")
    contract = BundleContract(
        name="manifest-workspace",
        version="0.2.0",
        description="fixture",
        category="productivity",
        components=Components(
            skills_root="skills",
            skills_include=("*/SKILL.md",),
            agents=(Component("executor", "agents/executor.md"),),
            hooks=(Component("session", "hooks/session.json"),),
            runtime=(Component("catalog", "runtime/catalog.py"),),
            guidance=(Component("orchestration", "guidance/orchestration.md"),),
        ),
        capabilities=Capabilities(
            mcp={
                CapabilityTier.REQUIRED: ("required-mcp",),
                CapabilityTier.DEFAULT: ("context7",),
                CapabilityTier.OPTIONAL: ("github",),
            },
            executables={
                CapabilityTier.REQUIRED: ("git",),
                CapabilityTier.DEFAULT: (),
                CapabilityTier.OPTIONAL: ("semgrep",),
            },
        ),
        compatibility={
            name: CompatibilityStatus("native") for name in AdapterRegistry.names()
        },
        provenance=Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
    )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source="fixture",
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(tmp_path), None
        ),
        release_root=tmp_path,
        repository_url="https://example.invalid/repo",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=(contract,),
        selected_optional=frozenset(),
        requested_harnesses=("claude",),
    )


@pytest.fixture
def complete_evidence() -> set[str]:
    return {
        "manifest-workspace:skill:help",
        "manifest-workspace:agent:executor",
        "manifest-workspace:hook:session",
        "manifest-workspace:runtime:catalog",
        "manifest-workspace:guidance:orchestration",
        "manifest-workspace:mcp:required-mcp",
        "manifest-workspace:mcp:context7",
        "manifest-workspace:executable:git",
    }


def test_missing_declared_component_is_blocked(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    complete_evidence.remove("manifest-workspace:agent:executor")

    result = FakeAdapter(complete_evidence).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert result.errors[0] == (
        "missing adapter evidence: manifest-workspace:agent:executor"
    )


def test_declared_component_identities_cover_every_contract_surface(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    result = verify_declared_components("claude", desired, complete_evidence)

    assert result.state is ResultState.READY
    assert set(result.capabilities) == complete_evidence
    assert set(result.capabilities.values()) == {"verified"}


def test_missing_required_capability_is_blocked(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    complete_evidence.remove("manifest-workspace:executable:git")

    result = verify_declared_components("claude", desired, complete_evidence)

    assert result.state is ResultState.BLOCKED
    assert "manifest-workspace:executable:git" in result.errors[0]


def test_missing_default_capability_is_degraded(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    complete_evidence.remove("manifest-workspace:mcp:context7")

    result = verify_declared_components("claude", desired, complete_evidence)

    assert result.state is ResultState.DEGRADED
    assert result.errors == (
        "missing default capability evidence: manifest-workspace:mcp:context7",
    )
    assert result.declared_degradations == ()


def test_unselected_optional_capability_requires_no_evidence(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    result = verify_declared_components("claude", desired, complete_evidence)

    assert "manifest-workspace:mcp:github" not in result.capabilities
    assert "manifest-workspace:executable:semgrep" not in result.capabilities


def test_selected_optional_capability_failure_is_warning_only(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    selected = DesiredState(
        **{
            **desired.__dict__,
            "selected_optional": frozenset({"github", "semgrep"}),
        }
    )

    result = verify_declared_components("claude", selected, complete_evidence)

    assert result.state is ResultState.READY
    assert result.errors == ()
    assert result.warnings == (
        "missing selected optional capability evidence: manifest-workspace:mcp:github",
        "missing selected optional capability evidence: "
        "manifest-workspace:executable:semgrep",
    )


def test_explicit_component_degradation_is_degraded_with_exact_reason(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    contract = desired.contracts[0]
    degraded_agent = Component(
        "executor",
        "agents/executor.md",
        {"claude": CompatibilityStatus("degraded", "agents are unavailable")},
    )
    changed_contract = BundleContract(
        **{
            **contract.__dict__,
            "components": Components(
                **{**contract.components.__dict__, "agents": (degraded_agent,)}
            ),
        }
    )
    changed_desired = DesiredState(
        **{**desired.__dict__, "contracts": (changed_contract,)}
    )
    complete_evidence.remove("manifest-workspace:agent:executor")

    result = verify_declared_components("claude", changed_desired, complete_evidence)

    assert result.state is ResultState.DEGRADED
    assert result.errors == ("agents are unavailable",)
    assert result.declared_degradations == ("agents are unavailable",)
    assert result.capabilities["manifest-workspace:agent:executor"] == "degraded"


def test_explicit_required_component_unsupported_is_blocked_independently(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    contract = desired.contracts[0]
    unsupported_agent = Component(
        "executor",
        "agents/executor.md",
        {"claude": CompatibilityStatus("unsupported", "agents are unavailable")},
    )
    changed_contract = BundleContract(
        **{
            **contract.__dict__,
            "components": Components(
                **{**contract.components.__dict__, "agents": (unsupported_agent,)}
            ),
        }
    )
    changed_desired = DesiredState(
        **{**desired.__dict__, "contracts": (changed_contract,)}
    )
    complete_evidence.remove("manifest-workspace:agent:executor")

    result = verify_declared_components("claude", changed_desired, complete_evidence)

    assert result.state is ResultState.BLOCKED
    assert result.errors == ("agents are unavailable",)
    assert result.capabilities["manifest-workspace:agent:executor"] == "unsupported"
    assert result.capabilities["manifest-workspace:skill:help"] == "verified"
    assert result.capabilities["manifest-workspace:executable:git"] == "verified"


def test_unsupported_required_bundle_is_blocked_and_excludes_optional_capabilities(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    contract = desired.contracts[0]
    compatibility = dict(contract.compatibility)
    compatibility["claude"] = CompatibilityStatus(
        "unsupported", "bundle activation is unavailable"
    )
    changed_contract = BundleContract(
        **{**contract.__dict__, "compatibility": compatibility}
    )
    changed_desired = DesiredState(
        **{**desired.__dict__, "contracts": (changed_contract,)}
    )

    result = verify_declared_components("claude", changed_desired, complete_evidence)

    assert result.state is ResultState.BLOCKED
    assert result.errors == ("bundle activation is unavailable",)
    assert "manifest-workspace:mcp:github" not in result.capabilities
    assert "manifest-workspace:executable:semgrep" not in result.capabilities


def test_required_plugins_are_blocked_when_missing(desired: DesiredState) -> None:
    result = verify_required_plugins("claude", desired, ())

    assert result.state is ResultState.BLOCKED
    assert result.errors == ("missing required plugin: manifest-workspace",)


def test_result_combination_preserves_all_diagnostics() -> None:
    blocked = HarnessResult(
        "claude", ResultState.BLOCKED, (), {}, ("blocked",), ("first warning",)
    )
    degraded = HarnessResult(
        "claude",
        ResultState.DEGRADED,
        ("manifest-workspace",),
        {"manifest-workspace:skill:help": "verified"},
        ("degraded",),
        ("second warning",),
        declared_degradations=("degraded",),
    )

    result = combine_results(blocked, degraded)

    assert result.state is ResultState.BLOCKED
    assert result.installed_plugin_ids == ("manifest-workspace",)
    assert result.errors == ("blocked", "degraded")
    assert result.warnings == ("first warning", "second warning")
    assert result.declared_degradations == ("degraded",)
