"""Journal authority, HMAC binding, and unfinished-saga recovery."""

import json
import shutil
from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    RepairCheckpoint,
    _read_journal,
    _recover_unfinished,
    _serialize_change,
    _serialize_handle,
    _serialize_owned,
    _write_journal,
)
from manifest_agent.codex_config import (
    apply_plugin_enabled,
    prepare_plugin_enabled,
    set_plugin_enabled,
)
from manifest_agent.codex_plugin_backup import (
    capture_plugin_backup,
    restore_plugin_backup,
)
from manifest_agent.codex_skill_cutover import (
    apply_codex_skill_cutover,
    commit_codex_skill_cutover,
    cutover_codex_skills,
    prepare_codex_skill_cutover,
)
from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
)
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    _installed_row,
)
from tests.python.manifest_agent.test_service_install import make_service_factory


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


def test_first_install_journal_creates_sentinel_bound_authority(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "state" / ".receipt.bootstrap-sync.json"
    journal.parent.mkdir()
    saga = ReconciliationSaga(
        "prepared",
        "codex",
        prior_receipt_digest=bootstrap_module.NO_PRIOR_RECEIPT_V1,
        target_identity="a" * 64,
    )

    _write_journal(journal, saga)

    key = journal.parent / "ownership.key"
    assert key.exists()
    assert key.stat().st_mode & 0o777 == 0o600
    assert (
        _read_journal(
            journal,
            expected_prior_receipt_digest=bootstrap_module.NO_PRIOR_RECEIPT_V1,
            expected_target_identity="a" * 64,
        )
        == saga
    )


@pytest.mark.parametrize(
    "tamper",
    (
        lambda document: document.__setitem__("phase", "committed"),
        lambda document: document.__setitem__("target_identity", "e" * 64),
        lambda document: document.__setitem__("prior_receipt_digest", "f" * 64),
        lambda document: document["harness_mutations"][0]["handle"]["target_inventory"][
            0
        ].__setitem__("version", "9.9.9"),
        lambda document: document["repairs"][0]["backup"].__setitem__(
            "archive_path", "/tmp/foreign.tar"
        ),
        lambda document: document["repairs"][0]["backup"].__setitem__(
            "archive_sha256", "0" * 64
        ),
        lambda document: document["repairs"][0]["backup"].__setitem__(
            "archive_size", document["repairs"][0]["backup"]["archive_size"] + 1
        ),
    ),
)
def test_journal_hmac_rejects_tampered_transaction_fields(
    tmp_path: Path, tamper
) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "data").write_text("fixture", encoding="utf-8")
    backup = capture_plugin_backup(_installed_row(plugin), {"HOME": str(tmp_path)})
    handle = AdapterMutationHandle(
        1,
        "gemini",
        "1",
        "b" * 64,
        (AdapterPluginState("manifest-workspace", "1.0.0", True),),
        (AdapterPluginState("manifest-workspace", "2.0.0", True),),
    )
    saga = ReconciliationSaga(
        "harness-convergence",
        "codex",
        repairs=(RepairCheckpoint("captured", backup.to_dict()),),
        harness_mutations=(
            HarnessMutationCheckpoint("gemini", "prepared", _serialize_handle(handle)),
        ),
        prior_receipt_digest="c" * 64,
        target_identity="d" * 64,
    )
    journal = tmp_path / "journal.json"
    _write_journal(journal, saga)
    document = json.loads(journal.read_text(encoding="utf-8"))
    tamper(document)
    journal.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RuntimeError, match="journal is invalid"):
        _read_journal(journal)


@pytest.mark.parametrize("key_bytes", (None, b"corrupt"))
def test_existing_journal_never_regenerates_missing_or_corrupt_authority(
    tmp_path: Path, key_bytes: bytes | None
) -> None:
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "prepared",
        "codex",
        prior_receipt_digest=bootstrap_module.NO_PRIOR_RECEIPT_V1,
        target_identity="a" * 64,
    )
    _write_journal(journal, saga)
    key = journal.parent / "ownership.key"
    if key_bytes is None:
        key.unlink()
    else:
        key.write_bytes(key_bytes)

    with pytest.raises(RuntimeError, match="journal is invalid"):
        _read_journal(journal)

    assert journal.exists()
    if key_bytes is None:
        assert not key.exists()
    else:
        assert key.read_bytes() == key_bytes


def test_unfinished_saga_restores_removed_plugin_config_and_skill_link(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    plugin = home / ".codex/plugins/manifest-workspace"
    plugin.mkdir(parents=True)
    (plugin / "SKILL.md").write_text("fixture", encoding="utf-8")
    backup = capture_plugin_backup(_installed_row(plugin), {"HOME": str(home)})
    plugin.rename(plugin.with_name("removed"))

    config = home / ".codex/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n',
        encoding="utf-8",
    )
    change = set_plugin_enabled(config, "i-have-adhd@i-have-adhd", False)

    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    cutover = cutover_codex_skills(home, source)

    journal = home / ".local/state/manifest/.receipt.bootstrap-sync.json"
    saga = ReconciliationSaga(
        "cutover-complete",
        "codex",
        (RepairCheckpoint("removed", backup.to_dict()),),
        _serialize_change(change),
        _serialize_owned(cutover),
    )
    _write_journal(journal, saga)

    recovered = _recover_unfinished(journal, saga, config)

    assert (plugin / "SKILL.md").read_text(encoding="utf-8") == "fixture"
    assert "enabled = true" in config.read_text(encoding="utf-8")
    assert skills.is_symlink()
    assert skills.resolve() == source
    assert recovered.phase == "prepared"
    assert recovered.repairs[0].phase == "restored"
    assert recovered.plugin_change is None
    assert recovered.cutover_entry is None


def test_captured_but_removed_crash_window_restores_backup(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "data").write_text("fixture", encoding="utf-8")
    backup = capture_plugin_backup(_installed_row(plugin), {"HOME": str(tmp_path)})
    plugin.rename(tmp_path / "removed")
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "plugin-repair",
        "codex",
        (RepairCheckpoint("captured", backup.to_dict()),),
    )
    _write_journal(journal, saga)

    recovered = _recover_unfinished(journal, saga, tmp_path / "config.toml")

    assert (plugin / "data").read_text(encoding="utf-8") == "fixture"
    assert recovered.repairs[0].phase == "restored"


def test_codex_cache_backup_restore_recreates_native_registration(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    installed = codex_home / "plugins/cache/manifest/manifest-workspace/0.2.0"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("cached plugin\n", encoding="utf-8")
    source = tmp_path / "marketplace/manifest-workspace"
    source.mkdir(parents=True)
    (source / "payload.txt").write_text("marketplace source\n", encoding="utf-8")
    row = {
        "pluginId": "manifest-workspace@manifest",
        "version": "0.2.0",
        "enabled": False,
        "installedPath": str(installed),
        "source": {"path": str(source)},
    }
    backup = capture_plugin_backup(
        row,
        {"CODEX_HOME": str(codex_home), "HOME": str(tmp_path / "home")},
    )
    config = codex_home / "config.toml"
    config.write_text('theme = "light"\n', encoding="utf-8")
    shutil.rmtree(installed)

    restore_plugin_backup(backup)

    assert (installed / "payload.txt").read_text(encoding="utf-8") == "cached plugin\n"
    text = config.read_text(encoding="utf-8")
    assert 'theme = "light"' in text
    assert '[plugins."manifest-workspace@manifest"]' in text
    assert "enabled = false" in text


def test_captured_crash_window_blocks_changed_target(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "data").write_text("fixture", encoding="utf-8")
    backup = capture_plugin_backup(_installed_row(plugin), {"HOME": str(tmp_path)})
    (plugin / "data").write_text("changed later", encoding="utf-8")
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "plugin-repair",
        "codex",
        (RepairCheckpoint("captured", backup.to_dict()),),
    )
    _write_journal(journal, saga)

    with pytest.raises(RuntimeError, match="installed target changed"):
        _recover_unfinished(journal, saga, tmp_path / "config.toml")

    assert journal.exists()


def test_committed_saga_removes_backup_only_after_receipt_phase(
    tmp_path: Path,
) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "data").write_text("fixture", encoding="utf-8")
    backup = capture_plugin_backup(_installed_row(plugin), {"HOME": str(tmp_path)})
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "committed",
        "codex",
        (RepairCheckpoint("added", backup.to_dict()),),
    )
    _write_journal(journal, saga)

    recovered = _recover_unfinished(journal, saga, tmp_path / "config.toml")

    assert not Path(backup.archive_path).exists()
    assert not journal.exists()
    assert recovered is None


def test_committed_cutover_cleanup_is_idempotent_after_backup_was_removed(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    legacy = home / ".codex/skills"
    legacy.symlink_to(source)
    entry = prepare_codex_skill_cutover(home, source)
    apply_codex_skill_cutover(entry, source)
    commit_codex_skill_cutover(entry)
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "committed", "codex", cutover_entry=_serialize_owned(entry)
    )
    _write_journal(journal, saga)

    recovered = _recover_unfinished(journal, saga, tmp_path / "config.toml")

    assert recovered is None
    assert not journal.exists()
    assert (home / ".codex/skills/.system").is_symlink()


def test_recovery_detects_config_applied_after_prepared_checkpoint(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n',
        encoding="utf-8",
    )
    change = prepare_plugin_enabled(config, "i-have-adhd@i-have-adhd", False)
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "upstream-prepared", "codex", plugin_change=_serialize_change(change)
    )
    _write_journal(journal, saga)
    apply_plugin_enabled(config, change)

    recovered = _recover_unfinished(journal, saga, config)

    assert "enabled = true" in config.read_text(encoding="utf-8")
    assert recovered.phase == "prepared"
    assert recovered.plugin_change is None


def test_recovery_blocks_ambiguous_config_and_retains_journal(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n',
        encoding="utf-8",
    )
    change = prepare_plugin_enabled(config, "i-have-adhd@i-have-adhd", False)
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "upstream-prepared", "codex", plugin_change=_serialize_change(change)
    )
    _write_journal(journal, saga)
    apply_plugin_enabled(config, change)
    config.write_text(
        config.read_text().replace("false", "true") + 'later = "user"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="owned field changed"):
        _recover_unfinished(journal, saga, config)

    assert journal.exists()


def test_recovery_detects_cutover_applied_after_prepared_checkpoint(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = prepare_codex_skill_cutover(home, source)
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "cutover-prepared", "codex", cutover_entry=_serialize_owned(entry)
    )
    _write_journal(journal, saga)
    apply_codex_skill_cutover(entry, source)

    recovered = _recover_unfinished(journal, saga, home / ".codex/config.toml")

    assert skills.is_symlink()
    assert skills.resolve() == source
    assert recovered.cutover_entry is None


def test_recovery_blocks_ambiguous_cutover_and_retains_backup_and_journal(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = prepare_codex_skill_cutover(home, source)
    journal = tmp_path / "journal.json"
    saga = ReconciliationSaga(
        "cutover-prepared", "codex", cutover_entry=_serialize_owned(entry)
    )
    _write_journal(journal, saga)
    apply_codex_skill_cutover(entry, source)
    (skills / "foreign").mkdir()

    with pytest.raises(RuntimeError, match="cutover recovery is ambiguous"):
        _recover_unfinished(journal, saga, home / ".codex/config.toml")

    assert journal.exists()
    assert (home / ".codex/.skills.manifest-cutover").is_symlink()
