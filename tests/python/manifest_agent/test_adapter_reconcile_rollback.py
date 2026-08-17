"""Contract tests for the shared harness adapter boundary and fixture CLI."""

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


# constitution: exempt C-SIZE -- one stateful fake pins both raced and exact rollback paths.
def test_rollback_removes_target_delta_and_restores_exact_prior_inventory(
    desired: DesiredState, tmp_path: Path
) -> None:
    addon = replace(desired.contracts[0], name="future-addon", version="3.0.0")
    addon_root = tmp_path / "plugins/future-addon"
    addon_root.mkdir(parents=True)
    (addon_root / "asset").write_text("target", encoding="utf-8")
    target = replace(
        desired,
        release_version="3.0.0",
        source_commit="c" * 40,
        archive_sha256="d" * 64,
        addon_contracts=(addon,),
    )

    class RecordingNativeRunner(CommandRunner):
        def __init__(self) -> None:
            self.calls = []
            self.adapter = None

        def run(self, argv, *, env=None):
            del env
            self.calls.append(tuple(argv))
            return CommandResult(tuple(argv), 0, "", "")

    class ExactAdapter(CapabilityAdapterMixin):
        name = "gemini"
        adapter_version = "1"

        def __init__(self) -> None:
            self.runner = RecordingNativeRunner()
            self._env = None
            self._which = lambda name: name
            self._native_mcp_inventory = {"required-mcp", "context7"}
            self.observed: tuple[AdapterPluginState, ...] = ()
            self.pathless_seam_calls: list[str] = []
            self.runner.adapter = self

        def install(self, selected):
            self.observed = self._desired_reconcile_inventory(selected)
            return HarnessResult(
                self.name,
                ResultState.READY,
                tuple(item.identifier for item in self.observed),
                {},
            )

        def inspect(self, selected):
            del selected
            return HarnessResult(
                self.name,
                ResultState.READY,
                tuple(item.identifier for item in self.observed),
                {},
            )

        def _native_reconcile_inventory(
            self, selected, *, capture_backups, identifiers=None
        ):
            del selected, capture_backups
            return tuple(
                item
                for item in self.observed
                if identifiers is None or item.identifier in identifiers
            )

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

        def _conditional_pathless_native_remove(self, expected, selected, command_argv):
            del selected
            self.pathless_seam_calls.append(expected.identifier)
            self._native_mutation_boundary(expected.identifier)
            matching = tuple(
                item for item in self.observed if item.identifier == expected.identifier
            )
            if len(matching) != 1 or self._reconcile_plugin_payload(
                matching[0]
            ) != self._reconcile_plugin_payload(expected):
                raise ValueError(
                    f"native state changed at the final mutation boundary for "
                    f"{expected.identifier}"
                )
            self.observed = tuple(
                item for item in self.observed if item.identifier != expected.identifier
            )
            command = self.runner.run(command_argv, env=self._env)
            if command.returncode != 0:
                raise ValueError("pathless conditional removal failed")
            return None

    adapter = ExactAdapter()
    receipt = HarnessReceipt(
        "gemini",
        "1",
        "fixture",
        tuple(contract.name for contract in desired.all_contracts),
        (),
        {},
        True,
    )
    adapter.observed = adapter._desired_reconcile_inventory(desired)
    handle = adapter.prepare_reconcile(receipt, desired, target)
    adapter.observed = handle.target_inventory

    def concurrent_change(identifier: str) -> None:
        assert identifier == "future-addon"
        adapter.observed = tuple(
            replace(item, version="4.0.0") if item.identifier == identifier else item
            for item in adapter.observed
        )

    adapter._native_mutation_boundary = concurrent_change
    raced = adapter.rollback_reconcile(handle, desired)

    assert raced.state is ResultState.BLOCKED
    assert adapter.runner.calls == []
    assert (
        next(
            item for item in adapter.observed if item.identifier == "future-addon"
        ).version
        == "4.0.0"
    )

    adapter.observed = handle.target_inventory
    adapter._native_mutation_boundary = lambda identifier: None

    result = adapter.rollback_reconcile(handle, desired)

    assert result.state is ResultState.READY
    assert adapter.runner.calls == [
        ("gemini", "extensions", "uninstall", "future-addon")
    ]
    assert tuple(item.identifier for item in adapter.observed) == (
        "manifest-workspace",
    )
    assert adapter.pathless_seam_calls == ["future-addon", "future-addon"]


def test_failed_rollback_restore_stays_resumable_not_permanently_blocked() -> None:
    """Rollback removes the target before restoring prior; a failed restore
    leaves the plugin absent with a verified prior backup still on disk.

    That state is resumable -- the next pass retries the restore. It used to
    classify as resumable only while the marketplace still pointed at target;
    once the marketplace had also been reverted the identical state fell
    through to "other" and blocked the installation permanently.
    """
    from manifest_agent.adapters.codex_reconcile_observe import (
        _prior_partial_entry,
        _target_partial_entry,
    )

    prior = AdapterPluginState(
        "manifest-docs", "1.0.0", True, rollback_data={"archive": "prior-archive"}
    )
    target = AdapterPluginState("manifest-docs", "2.0.0", True)

    # row is None: the native remove landed, the restore did not.
    assert _target_partial_entry(None, prior, target) is True
    assert _prior_partial_entry(None, prior, target) is True


def test_absent_plugin_without_a_prior_backup_is_still_not_resumable() -> None:
    """The relaxation must not swallow a genuinely unrecoverable absence."""
    from manifest_agent.adapters.codex_reconcile_observe import _prior_partial_entry

    prior = AdapterPluginState("manifest-docs", "1.0.0", True, rollback_data=None)
    target = AdapterPluginState("manifest-docs", "2.0.0", True)

    assert _prior_partial_entry(None, prior, target) is False


def test_unchanged_plugin_that_vanished_is_still_blocking_not_resumable() -> None:
    """Only plugins actually in the reconciliation diff can be mid-rollback.

    A plugin present unchanged in both prior and target was never rolled back,
    so its disappearance is real data loss and must keep blocking -- even if it
    carries stale rollback_data from some earlier unrelated operation.
    """
    from manifest_agent.adapters.codex_reconcile_observe import (
        _prior_partial_entry,
        _target_partial_entry,
    )

    unchanged = AdapterPluginState(
        "manifest-docs", "1.0.0", True, rollback_data={"archive": "stale"}
    )

    assert _prior_partial_entry(None, unchanged, unchanged) is False
    assert _target_partial_entry(None, unchanged, unchanged) is False
