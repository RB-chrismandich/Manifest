"""Contract tests for the shared harness adapter boundary and fixture CLI."""

from collections.abc import Mapping, Sequence
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
    capture_owned_file_backup,
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
    OwnedEntry,
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


# constitution: exempt C-SIZE -- setup and final-boundary race assertions form one CAS regression.
def test_cursor_owned_file_rollback_blocks_mutation_after_aggregate_cas(
    desired: DesiredState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent.adapters import capability_lifecycle as lifecycle

    home = tmp_path / "home"
    path = home / ".cursor/mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"before": true}\n', encoding="utf-8")
    plan = SimpleNamespace(selected_mcp=(), mcp_definitions={})
    monkeypatch.setattr(lifecycle, "resolve_capabilities", lambda *args, **kwargs: plan)

    class ConcurrentCursor(CapabilityAdapterMixin):
        name = "cursor"
        adapter_version = "1"
        runner = RaisingRunner(AssertionError("native removal must not run"))
        _native_mcp_inventory = ()

        def _which(self, name):
            return name

        def __init__(self) -> None:
            self._env = {"HOME": str(home), "XDG_STATE_HOME": str(tmp_path / "state")}
            self.inventory = (
                AdapterPluginState("manifest-marketplace", "target", True),
            )

        def _native_reconcile_inventory(
            self, selected, *, capture_backups, identifiers=None
        ):
            del selected, capture_backups, identifiers
            return self.inventory

        def _desired_reconcile_inventory(self, selected):
            del selected
            return self.inventory

        def install(self, selected):
            del selected
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

    adapter = ConcurrentCursor()
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "fixture",
        (),
        (OwnedEntry("mcp", "example", "manifest", str(path), "proof"),),
        {},
        True,
    )
    handle = adapter.prepare_reconcile(receipt, desired, desired)
    original_observe = adapter._observe_reconcile_cas

    def mutate_after_cas(handle_arg, selected, *, prior):
        result = original_observe(handle_arg, selected, prior=prior)
        if not prior and result is None:
            path.write_text("concurrent bytes\n", encoding="utf-8")
        return result

    adapter._observe_reconcile_cas = mutate_after_cas

    result = adapter.rollback_reconcile(handle, desired)

    assert result.state is ResultState.BLOCKED
    assert path.read_text(encoding="utf-8") == "concurrent bytes\n"
    assert "changed concurrently" in " ".join(result.errors)


def test_owned_file_rollback_preserves_edit_at_final_transition_boundary(
    desired: DesiredState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OwnedAdapter(CapabilityAdapterMixin):
        name = "devin"
        adapter_version = "1"

        def __init__(self) -> None:
            self._env = {
                "HOME": str(tmp_path),
                "XDG_STATE_HOME": str(tmp_path / "state"),
            }

    adapter = OwnedAdapter()
    target = tmp_path / "owned.txt"
    target.write_text("prior\n", encoding="utf-8")
    prior_backup, prior_mode, prior_digest = capture_owned_file_backup(
        target, adapter._env
    )
    prior = {
        "path": str(target),
        "type": "file",
        "mode": prior_mode,
        "digest": prior_digest,
        "restore": {"archive": prior_backup.to_dict()},
    }
    target.write_text("installed\n", encoding="utf-8")
    installed_backup, installed_mode, installed_digest = capture_owned_file_backup(
        target, adapter._env
    )
    installed = {
        "path": str(target),
        "type": "file",
        "mode": installed_mode,
        "digest": installed_digest,
        "restore": {"archive": installed_backup.to_dict()},
    }
    handle = AdapterMutationHandle(
        2,
        "devin",
        "1",
        "fixture",
        (),
        (),
        prior_owned_files=(prior,),
        target_owned_files=(installed,),
    )

    def concurrent_edit(path: Path) -> None:
        path.write_text("concurrent\n", encoding="utf-8")

    monkeypatch.setattr(adapter, "_owned_file_transition_boundary", concurrent_edit)

    result = adapter._restore_exact_prior_owned_files(handle)

    assert result.state is ResultState.BLOCKED
    assert target.read_text(encoding="utf-8") == "concurrent\n"
