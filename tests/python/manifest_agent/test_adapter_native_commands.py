"""Contract tests for the shared harness adapter boundary and fixture CLI."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters import (
    AdapterRegistry,
    Detection,
    native_command_result,
    run_native_command,
    verify_declared_components,
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


def test_nonzero_required_native_command_is_blocked(
    desired: DesiredState, complete_evidence: set[str]
) -> None:
    adapter = FakeAdapter(complete_evidence)
    adapter.runner.queue(returncode=9, stderr="native failure")

    result = adapter.install(desired)

    assert result.state is ResultState.BLOCKED
    assert "native failure" in result.errors[0]


def test_native_command_error_output_is_preserved_and_redacted() -> None:
    command = CommandResult(
        ("fake",),
        7,
        "partial output",
        "Authorization: Bearer native-secret",
    )

    result = native_command_result("claude", command, CapabilityTier.REQUIRED)

    assert result.state is ResultState.BLOCKED
    assert "partial output" in result.errors[0]
    assert "native-secret" not in result.errors[0]
    assert "[REDACTED]" in result.errors[0]


def test_default_native_command_failure_is_degraded() -> None:
    result = native_command_result(
        "claude",
        CommandResult(("fake",), 1, "", "default unavailable"),
        CapabilityTier.DEFAULT,
    )

    assert result.state is ResultState.DEGRADED
    assert result.errors == ("native command exited 1; stderr: default unavailable",)


def test_selected_optional_native_command_failure_is_warning_only() -> None:
    result = native_command_result(
        "claude",
        CommandResult(("fake",), 1, "", "optional unavailable"),
        CapabilityTier.OPTIONAL,
        selected=True,
    )

    assert result.state is ResultState.READY
    assert result.errors == ()
    assert "optional unavailable" in result.warnings[0]


@pytest.mark.parametrize("returncode", [0, 1])
def test_optional_native_command_must_be_explicitly_selected(returncode: int) -> None:
    result = native_command_result(
        "claude",
        CommandResult(("fake",), returncode, "", "should not run"),
        CapabilityTier.OPTIONAL,
    )

    assert result.state is ResultState.BLOCKED
    assert result.errors == ("optional native command was not explicitly selected",)


def test_unselected_optional_command_is_not_executed() -> None:
    runner = RaisingRunner(AssertionError("runner must not be called"))

    result = run_native_command(
        "claude", runner, ("fake", "optional"), CapabilityTier.OPTIONAL
    )

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []


@pytest.mark.parametrize(
    ("tier", "selected", "expected_state", "diagnostic_field"),
    [
        (CapabilityTier.REQUIRED, False, ResultState.BLOCKED, "errors"),
        (CapabilityTier.DEFAULT, False, ResultState.DEGRADED, "errors"),
        (CapabilityTier.OPTIONAL, True, ResultState.READY, "warnings"),
    ],
)
@pytest.mark.parametrize(
    "execution_error",
    [
        FileNotFoundError("--token native-exception-secret executable not found"),
        RuntimeError("--token native-exception-secret runner crashed"),
    ],
)
def test_native_execution_exceptions_are_classified_and_redacted(
    tier: CapabilityTier,
    selected: bool,
    expected_state: ResultState,
    diagnostic_field: str,
    execution_error: Exception,
) -> None:
    runner = RaisingRunner(execution_error)

    result = run_native_command(
        "claude",
        runner,
        ("missing-native", "list"),
        tier,
        selected=selected,
    )

    diagnostics = getattr(result, diagnostic_field)
    assert result.state is expected_state
    assert type(execution_error).__name__ in diagnostics[0]
    assert "native-exception-secret" not in diagnostics[0]
    assert "[REDACTED]" in diagnostics[0]
