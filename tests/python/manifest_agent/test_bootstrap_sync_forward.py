"""Forward-only bootstrap-sync crash recovery and content-digest repair tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.adapters.capability_reconcile_state import ReconcileStateMixin
from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    _read_journal,
    _serialize_handle,
    _write_journal,
)
from manifest_agent.codex_plugin_backup import plugin_tree_sha256
from manifest_agent.models import (
    AdapterPluginState,
    HarnessResult,
    ResultState,
)
from manifest_agent.release import resolve_release
from manifest_agent.state import read_receipt, receipt_digest
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    bump_release,
    legacy_skill_home,
)
from tests.python.manifest_agent.test_bootstrap_sync_cross_harness import (
    _installed_local_service,
    _local_git_checkout,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path):
    """Create isolated ManifestService instances rooted in tmp_path."""
    return make_service_factory(tmp_path)


@pytest.mark.parametrize(
    "crash_phase",
    (
        "upstream-prepared",
        "upstream-disabled",
        "cutover-prepared",
        "cutover-complete",
        "receipt-prepared",
    ),
)
def test_forward_only_crash_in_no_mutation_phase_recovers_and_converges(
    service_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_phase: str,
) -> None:
    """No-mutation forward-only journals recover without resolving prior release."""
    service, repo, _claude, _codex = _installed_local_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "mutated checkout\n", encoding="utf-8"
    )
    service.harnesses = ("codex",)
    home, _legacy = legacy_skill_home(tmp_path, monkeypatch)
    config = home / ".codex/config.toml"
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n',
        encoding="utf-8",
    )
    journal = bootstrap_module._journal_path(service.receipt_path)
    real_write = bootstrap_module._write_journal

    def crash_on_phase(path: Path, saga: ReconciliationSaga) -> None:
        real_write(path, saga)
        if saga.phase == crash_phase:
            raise SystemExit(f"injected {crash_phase} crash")

    monkeypatch.setattr(bootstrap_module, "_write_journal", crash_on_phase)
    with pytest.raises(SystemExit, match=crash_phase):
        service.bootstrap_sync()

    interrupted = _read_journal(journal)
    assert interrupted is not None
    assert interrupted.phase == crash_phase
    assert interrupted.harness_mutations == ()
    assert read_receipt(service.receipt_path) == previous

    monkeypatch.setattr(bootstrap_module, "_write_journal", real_write)
    restarted = service.bootstrap_sync()

    assert restarted.state is ResultState.READY, restarted.errors
    assert not journal.exists()
    updated = read_receipt(service.receipt_path)
    assert updated is not None and updated.source_dirty is True
    assert not (home / ".codex/skills").is_symlink()
    assert "enabled = false" in config.read_text(encoding="utf-8")
    owned_kinds = {
        entry.kind: entry for entry in updated.harnesses["codex"].owned_entries
    }
    assert "codex-skill-source" in owned_kinds
    assert (
        json.loads(owned_kinds["plugin-enabled-state"].previous_checksum)["previous"]
        is True
    )


def test_forward_only_restart_with_recorded_harness_mutation_still_refuses(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded harness mutations still fail closed when prior release is gone."""
    service, repo, claude, _codex = _installed_local_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    prior_desired, error = service._desired_state()
    assert error is None and prior_desired is not None
    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "mutated checkout\n", encoding="utf-8"
    )
    desired, error = service._desired_state()
    assert error is None and desired is not None
    handle = claude.prepare_reconcile(
        previous.harnesses["claude"], prior_desired, desired
    )
    journal = bootstrap_module._journal_path(service.receipt_path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "harness-prepared",
            "codex",
            harness_mutations=(
                HarnessMutationCheckpoint(
                    "claude", "prepared", _serialize_handle(handle)
                ),
            ),
            prior_receipt_digest=receipt_digest(previous),
            target_identity=bootstrap_module._target_identity(desired),
        ),
    )
    journal_before = journal.read_text(encoding="utf-8")
    service.harnesses = ("codex",)
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert (
        "prior release is unavailable for cross-harness compensation"
        in result.harnesses["codex"].errors[0]
    )
    assert journal.read_text(encoding="utf-8") == journal_before
    assert read_receipt(service.receipt_path) == previous


class _DigestAwareClaudeAdapter(ReconcileStateMixin, FakeAdapter):
    """Adapter exposing reconcile-inventory digests and plugin removal."""

    def __init__(self, installed_root: Path) -> None:
        super().__init__("claude", harness_result("claude"))
        self.installed_root = installed_root
        self.removed_ids: list[str] = []

    def install(self, desired):
        self.calls.append("install")
        for contract in desired.all_contracts:
            target = self.installed_root / contract.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(desired.bundle_path(contract.name), target)
        self.inspection = self.result
        return self.result

    def _native_reconcile_inventory(
        self, desired, *, capture_backups: bool = False, identifiers=None
    ) -> tuple[AdapterPluginState, ...]:
        del capture_backups
        items: list[AdapterPluginState] = []
        for contract in desired.all_contracts:
            plugin_id = f"{contract.name}@manifest"
            if identifiers is not None and plugin_id not in identifiers:
                continue
            path = self.installed_root / contract.name
            if not path.is_dir():
                continue
            items.append(
                AdapterPluginState(
                    plugin_id,
                    contract.version,
                    True,
                    installed_path=str(path),
                    installed_sha256=plugin_tree_sha256(path),
                    source_identity=self._expected_reconcile_source_identity(
                        desired, contract.name
                    ),
                )
            )
        return tuple(items)

    def _remove_reconcile_plugins(self, expected_items, desired) -> HarnessResult:
        del desired
        self.calls.append("remove")
        for item in expected_items:
            self.removed_ids.append(item.identifier)
            if item.installed_path is not None:
                shutil.rmtree(item.installed_path)
        return HarnessResult(self.name, ResultState.READY, (), {})


def _configure_undeclared_degraded_heal(adapter: FakeAdapter) -> None:
    adapter.inspection = HarnessResult(
        adapter.name,
        ResultState.DEGRADED,
        ("manifest-workspace@manifest",),
        {"manifest-workspace:mcp:context7": "missing"},
        errors=(
            "missing default capability evidence: manifest-workspace:mcp:context7",
        ),
    )
    original_install = adapter.install

    def heal_install(desired):
        installed = original_install(desired)
        adapter.inspection = installed
        return installed

    adapter.install = heal_install


def _digest_aware_local_service(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    repo = _local_git_checkout(tmp_path)
    installed_root = tmp_path / "claude-installed"
    claude = _DigestAwareClaudeAdapter(installed_root)
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.source = repo
    service.release_resolver = resolve_release
    assert service.install().state is ResultState.READY
    return service, repo, installed_root, claude


def test_forward_convergence_repairs_undeclared_degraded_inspection(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Undeclared DEGRADED inspection in forward-only sync must trigger install."""
    service, repo, claude, _codex = _installed_local_service(
        service_factory, tmp_path, monkeypatch
    )
    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "mutated checkout\n", encoding="utf-8"
    )
    _configure_undeclared_degraded_heal(claude)
    claude.calls.clear()
    service.harnesses = ("codex",)
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert claude.calls == ["detect", "inspect", "install", "inspect"]


def test_prepared_reconcile_repairs_undeclared_degraded_inspection(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Undeclared DEGRADED verify_reconcile must trigger apply_reconcile."""
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    bump_release(service)
    service.harnesses = ("codex",)
    _configure_undeclared_degraded_heal(claude)
    claude.calls.clear()
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert "apply" in claude.calls


def test_forward_convergence_removes_and_reinstalls_same_version_content_change(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same-version skill content edits trigger plugin removal and reinstall."""
    service, repo, installed_root, claude = _digest_aware_local_service(
        service_factory, tmp_path, monkeypatch
    )

    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "edited skill without version bump\n", encoding="utf-8"
    )
    claude.calls.clear()
    claude.removed_ids.clear()
    service.harnesses = ("codex",)
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert claude.removed_ids == ["manifest-workspace@manifest"]
    assert claude.calls == ["detect", "inspect", "remove", "install", "inspect"]
    assert (installed_root / "manifest-workspace" / "payload.txt").read_text(
        encoding="utf-8"
    ) == "edited skill without version bump\n"


def test_forward_convergence_skips_reinstall_when_content_digest_matches(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Identical installed plugin content skips removal and reinstall."""
    service, repo, installed_root, claude = _digest_aware_local_service(
        service_factory, tmp_path, monkeypatch
    )

    edited = "already synced content\n"
    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        edited, encoding="utf-8"
    )
    (installed_root / "manifest-workspace" / "payload.txt").write_text(
        edited, encoding="utf-8"
    )
    claude.calls.clear()
    claude.removed_ids.clear()
    service.harnesses = ("codex",)
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert claude.removed_ids == []
    assert claude.calls == ["detect", "inspect"]
