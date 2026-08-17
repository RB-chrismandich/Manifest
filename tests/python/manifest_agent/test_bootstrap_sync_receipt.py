"""Receipt promotion and prepared-target restart after crash."""

import json
from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.bootstrap_sync import (
    _read_journal,
)
from manifest_agent.models import (
    ResultState,
)
from manifest_agent.state import read_receipt, receipt_digest
from tests.python.manifest_agent._bootstrap_sync_fakes import (
    _ProbeAdapter,
)
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    _addon_desired,
    legacy_skill_home,
)
from tests.python.manifest_agent.test_service_install import (
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


def test_probe_failure_preserves_upstream_and_legacy_skill_source(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _ProbeAdapter(ResultState.BLOCKED)
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    desired = _addon_desired(service)
    service._desired_state = lambda receipt_release=None: (desired, None)
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    config = home / ".codex/config.toml"
    config.write_text('[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_SKILLS_DIR", str(source))

    report = service.bootstrap_sync()

    assert report.state is ResultState.BLOCKED
    assert adapter.calls == ["detect", "install", "inspect", "probe"]
    assert "enabled = true" in config.read_text(encoding="utf-8")
    assert skills.is_symlink()


def test_probe_and_prepared_journals_precede_migration_mutations(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _ProbeAdapter()
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    desired = _addon_desired(service)
    service._desired_state = lambda receipt_release=None: (desired, None)
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex/skills").symlink_to(source)
    config = home / ".codex/config.toml"
    config.write_text('[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_SKILLS_DIR", str(source))
    events = adapter.calls
    real_write = bootstrap_module._write_journal
    real_apply_config = bootstrap_module.apply_plugin_enabled
    real_apply_cutover = bootstrap_module.apply_codex_skill_cutover

    def record_write(path, saga):
        if saga.phase in {"upstream-prepared", "cutover-prepared"}:
            events.append(saga.phase)
        real_write(path, saga)

    def record_config(path, change):
        events.append("config-mutation")
        real_apply_config(path, change)

    def record_cutover(entry, expected):
        events.append("skill-cutover")
        real_apply_cutover(entry, expected)

    monkeypatch.setattr(bootstrap_module, "_write_journal", record_write)
    monkeypatch.setattr(bootstrap_module, "apply_plugin_enabled", record_config)
    monkeypatch.setattr(bootstrap_module, "apply_codex_skill_cutover", record_cutover)

    report = service.bootstrap_sync()

    assert report.state is ResultState.READY
    assert events.index("probe") < events.index("upstream-prepared")
    assert events.index("upstream-prepared") < events.index("config-mutation")
    assert events.index("cutover-prepared") < events.index("skill-cutover")


def test_restart_promotes_exact_receipt_prepared_target_after_post_rename_crash(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _ProbeAdapter()
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    desired = _addon_desired(service)
    service._desired_state = lambda receipt_release=None: (desired, None)
    _home, _legacy = legacy_skill_home(tmp_path, monkeypatch)
    real_write = bootstrap_module._write_journal
    crashed = False

    def fail_committed_checkpoint(path, saga):
        nonlocal crashed
        if saga.phase == "committed" and not crashed:
            crashed = True
            raise SystemExit("injected post-receipt-rename crash")
        real_write(path, saga)

    monkeypatch.setattr(bootstrap_module, "_write_journal", fail_committed_checkpoint)
    with pytest.raises(SystemExit, match="post-receipt-rename"):
        service.bootstrap_sync()

    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    journal_path = bootstrap_module._journal_path(service.receipt_path)
    prepared = _read_journal(journal_path)
    assert prepared is not None
    assert prepared.phase == "receipt-prepared"
    assert prepared.target_receipt_digest == receipt_digest(receipt)

    monkeypatch.setattr(bootstrap_module, "_write_journal", real_write)
    restarted = service.bootstrap_sync()

    assert restarted.state is ResultState.READY
    assert not journal_path.exists()
    assert read_receipt(service.receipt_path) == receipt


def test_receipt_directory_fsync_failure_preserves_target_for_restart(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent import state as state_module

    adapter = _ProbeAdapter()
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    desired = _addon_desired(service)
    service._desired_state = lambda receipt_release=None: (desired, None)
    home, _legacy = legacy_skill_home(tmp_path, monkeypatch)
    real_fsync = state_module._fsync_directory
    failed = False
    receipt_renamed = False
    real_replace = state_module.os.replace

    def record_receipt_replace(source_path, destination_path) -> None:
        nonlocal receipt_renamed
        real_replace(source_path, destination_path)
        if Path(destination_path) == service.receipt_path:
            receipt_renamed = True

    def fail_receipt_directory_fsync(path: Path) -> None:
        nonlocal failed
        if path == service.receipt_path.parent and receipt_renamed and not failed:
            failed = True
            raise OSError("injected receipt directory fsync failure")
        real_fsync(path)

    monkeypatch.setattr(state_module.os, "replace", record_receipt_replace)
    monkeypatch.setattr(state_module, "_fsync_directory", fail_receipt_directory_fsync)

    first = service.bootstrap_sync()

    assert first.state is ResultState.BLOCKED
    visible = read_receipt(service.receipt_path)
    assert visible is not None
    journal_path = bootstrap_module._journal_path(service.receipt_path)
    prepared = _read_journal(journal_path)
    assert prepared is not None and prepared.phase == "receipt-prepared"
    assert prepared.target_receipt_digest == receipt_digest(visible)
    assert (home / ".codex/skills/.system").exists()

    monkeypatch.setattr(state_module, "_fsync_directory", real_fsync)
    monkeypatch.setattr(state_module.os, "replace", real_replace)
    restarted = service.bootstrap_sync()

    assert restarted.state is ResultState.READY
    assert not journal_path.exists()
    assert read_receipt(service.receipt_path) == visible


def test_absent_upstream_enabled_state_is_receipt_owned_for_exact_restore(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _ProbeAdapter()
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    desired = _addon_desired(service)
    service._desired_state = lambda receipt_release=None: (desired, None)
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex/skills").symlink_to(source)
    config = home / ".codex/config.toml"
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nchannel = "stable"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_SKILLS_DIR", str(source))

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    owned = next(
        entry
        for entry in receipt.harnesses["codex"].owned_entries
        if entry.kind == "plugin-enabled-state"
    )
    metadata = json.loads(owned.previous_checksum)
    assert metadata["previous"] is None
    assert metadata["current"] is False
    assert metadata["table_existed"] is True
    assert metadata["separator_added"] is False
