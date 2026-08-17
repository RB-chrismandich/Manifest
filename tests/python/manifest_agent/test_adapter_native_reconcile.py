"""Contract tests for the shared harness adapter boundary and fixture CLI."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from manifest_agent.adapters import (
    AdapterRegistry,
    Detection,
    native_command_result,
    verify_declared_components,
)
from manifest_agent.adapters.capability_lifecycle import CapabilityAdapterMixin
from manifest_agent.codex_plugin_backup import (
    plugin_tree_sha256,
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
        from manifest_agent.models import AdapterPluginState

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


def test_expected_executable_target_uses_deterministic_install_path_not_prior_which(
    desired: DesiredState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent.adapters import capability_lifecycle as lifecycle

    target_bin = tmp_path / "managed-bin"
    prior_bin = tmp_path / "prior-bin" / "tool"
    target = target_bin / "tool"
    observed = {"tool": str(prior_bin)}
    plan = SimpleNamespace(
        selected_mcp=(),
        selected_executables=("tool",),
        executable_definitions={
            "tool": SimpleNamespace(executable="tool", manager="uv-tool")
        },
    )
    monkeypatch.setattr(lifecycle, "resolve_capabilities", lambda *args, **kwargs: plan)

    class ExecutableCasAdapter(CapabilityAdapterMixin):
        name = "gemini"
        adapter_version = "1"
        _native_mcp_inventory = ()

        def __init__(self) -> None:
            self._env = {"UV_TOOL_BIN_DIR": str(target_bin)}
            self._which = lambda name: observed.get(name)

    adapter = ExecutableCasAdapter()
    expected = adapter._expected_reconcile_capability_state(desired)

    assert expected == {"executable:tool": str(target.resolve())}
    assert adapter._observe_reconcile_capability_keys(expected) == {
        "executable:tool": str(prior_bin.resolve())
    }
    observed["tool"] = str(target)
    assert adapter._observe_reconcile_capability_keys(expected) == expected


def test_native_removal_preserves_change_at_final_mutation_boundary(
    desired: DesiredState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "native/example"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("prior\n", encoding="utf-8")
    expected = AdapterPluginState(
        "example",
        "1.0.0",
        True,
        installed_path=str(installed),
        installed_sha256=plugin_tree_sha256(installed),
        source_identity="prior",
    )

    class NativeAdapter(CapabilityAdapterMixin):
        name = "gemini"
        adapter_version = "1"

        def __init__(self) -> None:
            self._env = {"XDG_STATE_HOME": str(tmp_path / "state")}
            self.inventory = (expected,)
            self.runner = RaisingRunner(AssertionError("remove must not run"))

        def _native_reconcile_inventory(
            self, selected, *, capture_backups, identifiers=None
        ):
            del selected, capture_backups, identifiers
            if not installed.is_dir():
                return ()
            return (
                replace(
                    self.inventory[0], installed_sha256=plugin_tree_sha256(installed)
                ),
            )

    adapter = NativeAdapter()

    def concurrent_native_change(identifier: str) -> None:
        assert identifier == "example"
        displaced = installed.with_name("example-prior")
        installed.rename(displaced)
        installed.mkdir()
        (installed / "payload.txt").write_text("concurrent\n", encoding="utf-8")

    monkeypatch.setattr(adapter, "_native_mutation_boundary", concurrent_native_change)

    result = adapter._remove_reconcile_plugins((expected,), desired)

    assert result.state is ResultState.BLOCKED
    assert "final mutation boundary" in " ".join(result.errors)
    assert (installed / "payload.txt").read_text(encoding="utf-8") == "concurrent\n"
    assert adapter.runner.calls == []


# constitution: exempt C-SIZE -- the local adapter fake and its full no-remove transcript are one case.
def test_cursor_reconcile_replaces_changed_marketplace_without_remove(
    desired: DesiredState,
) -> None:
    target = replace(
        desired,
        release_version="3.0.0",
        source_commit="c" * 40,
        archive_sha256="d" * 64,
    )

    class CursorAdapter(CapabilityAdapterMixin):
        name = "cursor"
        adapter_version = "1"

        def __init__(self) -> None:
            self.runner = RaisingRunner(AssertionError("remove must not run"))
            self._env = None
            self._which = lambda name: name
            self._native_mcp_inventory = ()
            self.observed = self._desired_reconcile_inventory(desired)

        def _desired_reconcile_inventory(self, selected):
            return (
                AdapterPluginState(
                    "manifest-marketplace",
                    selected.source_commit,
                    True,
                    source_identity=selected.repository_url,
                ),
            )

        def _native_reconcile_inventory(
            self, selected, *, capture_backups, identifiers=None
        ):
            del selected, capture_backups, identifiers
            return self.observed

        def install(self, selected):
            self.observed = self._desired_reconcile_inventory(selected)
            return HarnessResult(self.name, ResultState.READY, (), {})

        def inspect(self, selected):
            del selected
            return HarnessResult(self.name, ResultState.READY, (), {})

        def _reconcile_capability_state(self, selected):
            del selected
            return {}

        def _expected_reconcile_capability_state(self, selected):
            del selected
            return {}

        def _expected_reconcile_owned_files(self, receipt, selected):
            del receipt, selected
            return ()

        def _expected_reconcile_owned_files_from_handle(self, handle, selected):
            del handle, selected
            return ()

    adapter = CursorAdapter()
    receipt = HarnessReceipt("cursor", "1", "fixture", (), (), {}, True)
    handle = adapter.prepare_reconcile(receipt, desired, target)

    assert adapter.apply_reconcile(handle, target).state is ResultState.READY
    assert adapter.rollback_reconcile(handle, desired).state is ResultState.READY
    assert adapter.runner.calls == []
