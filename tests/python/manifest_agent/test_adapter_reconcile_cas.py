"""Contract tests for the shared harness adapter boundary and fixture CLI."""

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters import (
    AdapterRegistry,
    Detection,
    native_command_result,
    verify_declared_components,
)
from manifest_agent.adapters.capability_lifecycle import CapabilityAdapterMixin
from manifest_agent.codex_plugin_backup import (
    capture_plugin_backup,
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


# constitution: exempt C-SIZE -- the local native fake and prepare/apply/rollback transcript are inseparable.
def test_generic_reconcile_uses_exact_cas_and_authenticated_backup(
    desired: DesiredState, tmp_path: Path
) -> None:
    prior_contract = desired.contracts[0]
    target_root = tmp_path / "target-release"
    target_bundle = target_root / "plugins" / prior_contract.name
    target_bundle.mkdir(parents=True)
    (target_bundle / "payload.txt").write_text("target bytes\n", encoding="utf-8")
    target_contract = replace(prior_contract, version="3.0.0")
    target = replace(
        desired,
        release_version="3.0.0",
        source_commit="c" * 40,
        archive_sha256="d" * 64,
        release_root=target_root,
        marketplace_source=replace(desired.marketplace_source, source=str(target_root)),
        contracts=(target_contract,),
    )
    installed = tmp_path / "native-cache" / prior_contract.name
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("exact observed prior\n", encoding="utf-8")

    class BackupRunner(CommandRunner):
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def run(self, argv, *, env=None):
            del env
            command = tuple(argv)
            self.calls.append(command)
            if command == (
                "gemini",
                "extensions",
                "uninstall",
                prior_contract.name,
            ):
                shutil.rmtree(installed)
                return CommandResult(command, 0, "", "")
            raise AssertionError(f"unexpected command: {command}")

    class BackupAdapter(CapabilityAdapterMixin):
        name = "gemini"
        adapter_version = "1"

        def __init__(self) -> None:
            self.runner = BackupRunner()
            self._env = {"XDG_STATE_HOME": str(tmp_path / "state")}
            self._which = lambda name: name
            self._native_mcp_inventory = ()
            self.version = prior_contract.version
            self.source = str(desired.bundle_path(prior_contract.name))

        def install(self, selected):
            source = selected.bundle_path(prior_contract.name)
            shutil.copytree(source, installed)
            contract = next(
                item
                for item in selected.all_contracts
                if item.name == prior_contract.name
            )
            self.version = contract.version
            self.source = str(source)
            return HarnessResult(
                self.name, ResultState.READY, (prior_contract.name,), {}
            )

        def inspect(self, selected):
            del selected
            return HarnessResult(
                self.name, ResultState.READY, (prior_contract.name,), {}
            )

        def _native_reconcile_inventory(
            self, selected, *, capture_backups, identifiers=None
        ):
            del selected
            if identifiers is not None and prior_contract.name not in identifiers:
                return ()
            if not installed.exists():
                return ()
            backup = None
            if capture_backups:
                backup = capture_plugin_backup(
                    {
                        "pluginId": prior_contract.name,
                        "version": self.version,
                        "enabled": True,
                        "source": {"path": str(installed)},
                    },
                    self._env,
                    require_manifest_suffix=False,
                ).to_dict()
            return (
                AdapterPluginState(
                    prior_contract.name,
                    self.version,
                    True,
                    rollback_data=backup,
                    installed_path=str(installed),
                    installed_sha256=plugin_tree_sha256(installed),
                    source_identity=self.source,
                ),
            )

        def _expected_reconcile_source_identity(self, selected, bundle):
            return str(selected.bundle_path(bundle))

        def _reconcile_capability_state(self, selected):
            del selected
            return {}

        def _expected_reconcile_capability_state(self, selected):
            del selected
            return {}

    adapter = BackupAdapter()
    receipt = HarnessReceipt(
        "gemini",
        "1",
        "fixture",
        (prior_contract.name,),
        (),
        {},
        True,
    )
    handle = adapter.prepare_reconcile(receipt, desired, target)

    assert handle.schema_version == 2
    assert handle.prior_cas and handle.target_cas
    assert handle.prior_inventory[0].rollback_data is not None
    assert handle.prior_inventory[0].source_identity == str(
        desired.bundle_path(prior_contract.name)
    )

    (installed / "payload.txt").write_text("changed after prepare\n", encoding="utf-8")
    changed_prior = adapter.apply_reconcile(handle, target)
    assert changed_prior.state is ResultState.BLOCKED
    assert any(
        "changed after reconciliation prepare" in error
        for error in changed_prior.errors
    )
    assert adapter.runner.calls == []

    shutil.rmtree(installed)
    shutil.copytree(target_bundle, installed)
    adapter.version = target_contract.version
    adapter.source = str(target_bundle)
    (installed / "payload.txt").write_text("changed after apply\n", encoding="utf-8")
    changed_target = adapter.rollback_reconcile(handle, desired)
    assert changed_target.state is ResultState.BLOCKED
    assert any("exact prepared target" in error for error in changed_target.errors)
    assert adapter.runner.calls == []

    shutil.rmtree(installed)
    shutil.copytree(target_bundle, installed)
    exact_target = adapter.rollback_reconcile(handle, desired)

    assert exact_target.state is ResultState.READY
    assert adapter.runner.calls == [
        ("gemini", "extensions", "uninstall", prior_contract.name)
    ]
    assert (installed / "payload.txt").read_text(encoding="utf-8") == (
        "exact observed prior\n"
    )
    assert plugin_tree_sha256(installed) == handle.prior_inventory[0].installed_sha256


def test_failed_install_after_removal_still_reports_the_removal() -> None:
    """A reconcile that removed plugins then failed to install must say so.

    Returning only the install result hides a mutation that already landed:
    the plugins are gone, but the caller's receipt/diagnostics would show an
    empty removal set and understate the blast radius of the failure.
    """
    import inspect

    from manifest_agent.adapters.capability_reconcile_lifecycle import (
        ReconcileLifecycleMixin,
    )

    source = inspect.getsource(ReconcileLifecycleMixin.apply_reconcile)
    install_failure_branch = source.split("installed = self.install(desired)", 1)[1]
    guard, _, _ = install_failure_branch.partition("target_check")

    assert "combine_results(removed, installed)" in guard, (
        "the install-failure branch must combine the completed removal into "
        "its result, like every other exit path in apply_reconcile"
    )
