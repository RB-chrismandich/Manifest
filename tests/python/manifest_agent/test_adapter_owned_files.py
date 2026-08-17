"""Contract tests for the shared harness adapter boundary and fixture CLI."""

import hashlib
import json
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
    CodexPluginBackupError,
    OwnedFileBackup,
    capture_owned_file_backup,
    read_owned_file_backup,
    remove_owned_file_backup,
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


# constitution: exempt C-SIZE -- one assertion matrix pins every field in the owned-file CAS.
def test_cursor_target_owned_file_cas_tracks_exact_bytes_mode_type_and_path(
    desired: DesiredState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent.adapters import capability_lifecycle as lifecycle

    home = tmp_path / "home"
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"unrelated": {"keep": true}}\n', encoding="utf-8")
    path.chmod(0o644)
    plan = SimpleNamespace(
        selected_mcp=("example",),
        mcp_definitions={
            "example": SimpleNamespace(
                transport="http", url="https://example.invalid/mcp"
            )
        },
    )
    monkeypatch.setattr(lifecycle, "resolve_capabilities", lambda *args, **kwargs: plan)

    class CursorCasAdapter(CapabilityAdapterMixin):
        name = "cursor"
        adapter_version = "1"
        _native_mcp_inventory = ()

        def __init__(self) -> None:
            self._env = {"HOME": str(home)}

    adapter = CursorCasAdapter()
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "fixture",
        (),
        (OwnedEntry("mcp", "example", "manifest", str(path), "proof"),),
        {},
        True,
    )
    prior = adapter._capture_receipt_owned_files(receipt)
    target = adapter._expected_reconcile_owned_files_from_prior(prior, desired)
    document = {
        "unrelated": {"keep": True},
        "mcpServers": {"manifest-example": {"url": "https://example.invalid/mcp"}},
    }
    target_bytes = (json.dumps(document, indent=2) + "\n").encode()

    assert target == (
        {
            "path": str(path),
            "type": "file",
            "mode": 0o600,
            "digest": hashlib.sha256(target_bytes).hexdigest(),
        },
    )
    restore = prior[0]["restore"]
    assert isinstance(restore, dict)
    assert "archive" in restore
    assert "content_b64" not in restore
    target_cas = adapter._reconcile_cas((), {}, target)
    for changed in (
        ({**target[0], "digest": "0" * 64},),
        ({**target[0], "mode": 0o644},),
        ({**target[0], "type": "symlink"},),
        ({**target[0], "path": str(tmp_path / "relocated.json")},),
    ):
        assert adapter._reconcile_cas((), {}, changed) != target_cas


def test_owned_file_capture_rejects_symlink_and_oversized_sources(
    tmp_path: Path,
) -> None:
    class OwnedAdapter(CapabilityAdapterMixin):
        name = "cursor"
        adapter_version = "1"

        def __init__(self) -> None:
            self._env = {
                "HOME": str(tmp_path),
                "XDG_STATE_HOME": str(tmp_path / "state"),
            }

    adapter = OwnedAdapter()
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "fixture",
        (),
        (OwnedEntry("mcp", "example", "manifest", str(link), "proof"),),
        {},
        True,
    )

    with pytest.raises(ValueError, match="not backup-safe"):
        adapter._capture_receipt_owned_files(receipt)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    receipt = replace(
        receipt,
        owned_entries=(
            OwnedEntry("mcp", "example", "manifest", str(oversized), "proof"),
        ),
    )
    with pytest.raises(ValueError, match="not backup-safe"):
        adapter._capture_receipt_owned_files(receipt)


def test_owned_archive_entry_swap_is_rejected_at_final_open_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent import codex_plugin_backup as backup_module

    env = {"HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state")}
    source = tmp_path / "source.txt"
    source.write_text("original\n", encoding="utf-8")
    backup, _mode, _digest = capture_owned_file_backup(source, env)
    outside = tmp_path / "outside.txt"
    outside.write_text("attacker\n", encoding="utf-8")

    def swap_entry(path: Path) -> None:
        path.unlink()
        path.symlink_to(outside)

    monkeypatch.setattr(backup_module, "_owned_archive_boundary", swap_entry)

    with pytest.raises(CodexPluginBackupError, match="backup is missing"):
        read_owned_file_backup(OwnedFileBackup.from_dict(backup.to_dict()), env)
    assert outside.read_text(encoding="utf-8") == "attacker\n"


def test_owned_archive_intermediate_directory_swap_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent import codex_plugin_backup as backup_module

    env = {"HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state")}
    source = tmp_path / "source.txt"
    source.write_text("original\n", encoding="utf-8")
    backup, _mode, _digest = capture_owned_file_backup(source, env)
    state = tmp_path / "state"
    displaced = tmp_path / "state-displaced"
    outside = tmp_path / "outside-state"
    outside.mkdir()
    swapped = False

    def swap_intermediate(_root: Path, component: str) -> None:
        nonlocal swapped
        if component == "state" and not swapped:
            swapped = True
            state.rename(displaced)
            state.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(
        backup_module, "_owned_archive_traversal_boundary", swap_intermediate
    )

    with pytest.raises(CodexPluginBackupError):
        read_owned_file_backup(OwnedFileBackup.from_dict(backup.to_dict()), env)


def test_owned_archive_removal_preserves_entry_swapped_at_quarantine_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent import codex_plugin_backup as backup_module

    env = {"HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state")}
    source = tmp_path / "source.txt"
    source.write_text("original\n", encoding="utf-8")
    backup, _mode, _digest = capture_owned_file_backup(source, env)
    archive = Path(backup.archive_path)
    displaced = archive.with_name(f"{archive.name}.displaced")

    def swap_entry(path: Path) -> None:
        path.rename(displaced)
        path.write_text("attacker\n", encoding="utf-8")

    monkeypatch.setattr(backup_module, "_owned_archive_remove_boundary", swap_entry)

    with pytest.raises(CodexPluginBackupError, match="final removal boundary"):
        remove_owned_file_backup(backup, env)

    assert archive.read_text(encoding="utf-8") == "attacker\n"
    assert displaced.read_text(encoding="utf-8") == "original\n"


def test_owned_archive_removal_uses_held_root_after_final_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent import codex_plugin_backup as backup_module

    env = {"HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state")}
    source = tmp_path / "source.txt"
    source.write_text("original\n", encoding="utf-8")
    backup, _mode, _digest = capture_owned_file_backup(source, env)
    archive = Path(backup.archive_path)
    root = archive.parent
    displaced_root = root.with_name(f"{root.name}-displaced")
    replacement_root = root.with_name(f"{root.name}-replacement")
    replacement_root.mkdir()
    replacement_entry = replacement_root / archive.name
    replacement_entry.write_text("attacker\n", encoding="utf-8")

    def swap_root(_path: Path) -> None:
        root.rename(displaced_root)
        replacement_root.rename(root)

    monkeypatch.setattr(
        backup_module, "_owned_archive_remove_quarantined_boundary", swap_root
    )

    remove_owned_file_backup(backup, env)

    assert not any(displaced_root.iterdir())
    assert archive.read_text(encoding="utf-8") == "attacker\n"
