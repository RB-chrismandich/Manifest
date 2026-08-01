"""Contract tests for the shared harness adapter boundary and fixture CLI."""

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters import (
    AdapterRegistry,
    Detection,
    HarnessAdapter,
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
    BundleContract,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)


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


class FakeAdapter:
    name = "claude"

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

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        del receipt
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
                CapabilityTier.DEFAULT: ("graphify",),
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
        "manifest-workspace:executable:graphify",
    }


def test_registry_has_exact_supported_harnesses() -> None:
    assert AdapterRegistry.names() == (
        "claude",
        "codex",
        "gemini",
        "cursor",
        "antigravity",
        "devin",
    )


def test_fake_adapter_satisfies_runtime_protocol(complete_evidence: set[str]) -> None:
    assert isinstance(FakeAdapter(complete_evidence), HarnessAdapter)


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


def test_optional_native_command_must_be_explicitly_selected() -> None:
    with pytest.raises(ValueError, match="explicitly selected"):
        native_command_result(
            "claude",
            CommandResult(("fake",), 1, "", "should not run"),
            CapabilityTier.OPTIONAL,
        )


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


@pytest.mark.parametrize("mode", ["degraded", "unsupported"])
def test_explicit_component_compatibility_is_degraded_with_exact_reason(
    mode: str, desired: DesiredState, complete_evidence: set[str]
) -> None:
    contract = desired.contracts[0]
    degraded_agent = Component(
        "executor",
        "agents/executor.md",
        {"claude": CompatibilityStatus(mode, "agents are unavailable")},
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
    assert result.capabilities["manifest-workspace:agent:executor"] == mode


def test_bundle_degradation_excludes_unselected_optional_capabilities(
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

    assert result.state is ResultState.DEGRADED
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
    )

    result = combine_results(blocked, degraded)

    assert result.state is ResultState.BLOCKED
    assert result.installed_plugin_ids == ("manifest-workspace",)
    assert result.errors == ("blocked", "degraded")
    assert result.warnings == ("first warning", "second warning")


def test_harness_stub_is_response_driven_and_logs_json_argv(tmp_path: Path) -> None:
    stub = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
    log = tmp_path / "argv.jsonl"
    env = {
        "PATH": os.environ["PATH"],
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_RESPONSES": json.dumps(
            {"stdout": "listed\n", "stderr": "warning\n", "returncode": 3}
        ),
    }

    result = subprocess.run(
        (str(stub), "plugin", "list", "argument with spaces"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 3
    assert result.stdout == "listed\n"
    assert result.stderr == "warning\n"
    assert json.loads(log.read_text(encoding="utf-8")) == [
        "harness-stub",
        "plugin",
        "list",
        "argument with spaces",
    ]


def test_harness_stub_selects_an_argv_specific_response(tmp_path: Path) -> None:
    stub = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
    log = tmp_path / "argv.jsonl"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "isolated-home"),
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_RESPONSES": json.dumps(
            {
                "responses": [
                    {"argv": ["plugin", "list"], "stdout": "selected"},
                ],
                "default": {"stderr": "unexpected", "returncode": 9},
            }
        ),
    }

    result = subprocess.run(
        (str(stub), "plugin", "list"),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert result.stdout == "selected"
    assert result.stderr == ""
