"""Receipt promotion and prepared-target restart after crash."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    _read_journal,
    _serialize_handle,
    _write_journal,
)
from manifest_agent.models import (
    HarnessResult,
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
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


def test_user_managed_codex_skills_sync_without_cutover_ownership(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _ProbeAdapter()
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    desired = _addon_desired(service)
    service._desired_state = lambda receipt_release=None: (desired, None)
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    skills = home / ".codex/skills"
    (skills / ".system").mkdir(parents=True)
    skill = skills / "my-skill/SKILL.md"
    skill.parent.mkdir()
    contents = b"user-owned skill\n"
    skill.write_bytes(contents)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_SKILLS_DIR", str(source))

    report = service.bootstrap_sync()

    assert report.state is ResultState.READY
    assert skill.read_bytes() == contents
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert all(
        entry.kind != "codex-skill-source"
        for entry in receipt.harnesses["codex"].owned_entries
    )
    journal = bootstrap_module._journal_path(service.receipt_path)
    if journal.exists():
        assert _read_journal(journal).cutover_entry is None


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


def _installed_codex_service(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    service.harnesses = ("codex",)
    legacy_skill_home(tmp_path, monkeypatch)
    journal = bootstrap_module._journal_path(service.receipt_path)
    return service, claude, codex, journal


def test_stale_empty_prepared_journal_is_unlinked_and_sync_proceeds(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _claude, codex, journal = _installed_codex_service(
        service_factory, tmp_path, monkeypatch
    )
    _write_journal(
        journal,
        ReconciliationSaga(
            "prepared",
            "codex",
            prior_receipt_digest="b" * 64,
            target_identity="c" * 64,
        ),
    )
    codex.calls.clear()

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert not journal.exists()
    assert "install" in codex.calls


def test_non_empty_prepared_journal_with_stale_binding_is_refused(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, codex, journal = _installed_codex_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    desired, error = service._desired_state()
    assert error is None and desired is not None
    handle = claude.prepare_reconcile(previous.harnesses["claude"], desired, desired)
    non_empty = ReconciliationSaga(
        "prepared",
        "codex",
        harness_mutations=(
            HarnessMutationCheckpoint("claude", "prepared", _serialize_handle(handle)),
        ),
        prior_receipt_digest="b" * 64,
        target_identity=bootstrap_module._target_identity(desired),
    )
    _write_journal(journal, non_empty)
    journal_before = journal.read_text(encoding="utf-8")
    codex.calls.clear()

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert (
        "receipt/target binding does not match" in result.harnesses["codex"].errors[0]
    )
    assert journal.read_text(encoding="utf-8") == journal_before
    assert "install" not in codex.calls


def test_mid_flight_journal_without_mutations_is_refused(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _claude, codex, journal = _installed_codex_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    mid_flight = ReconciliationSaga(
        "harness-convergence",
        "codex",
        prior_receipt_digest=receipt_digest(previous),
        target_identity="c" * 64,
    )
    _write_journal(journal, mid_flight)
    codex.calls.clear()

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert "unrecoverable state" in result.harnesses["codex"].errors[0]
    assert _read_journal(journal) == mid_flight
    assert "install" not in codex.calls


def test_corrupt_journal_is_refused_and_preserved(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _claude, codex, journal = _installed_codex_service(
        service_factory, tmp_path, monkeypatch
    )
    journal.write_text("{corrupt-json\n", encoding="utf-8")
    codex.calls.clear()

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert (
        "bootstrap reconciliation journal is invalid"
        in result.harnesses["codex"].errors[0]
    )
    assert journal.read_text(encoding="utf-8") == "{corrupt-json\n"
    assert "install" not in codex.calls


def test_durable_codex_recovers_empty_journal_on_unresolvable_local_receipt(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    adapter = _ProbeAdapter()
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    initial = replace(_addon_desired(service), release_version="local-111111111111")
    service._desired_state = lambda selector=None, *, exact_release=False: (
        (None, "ReleaseError: published release selector must be an immutable version")
        if exact_release
        else (initial, None)
    )
    legacy_skill_home(tmp_path, monkeypatch)
    assert service.install().state is ResultState.READY
    adapter.runner = object()
    mutated = replace(
        initial,
        release_version="local-222222222222",
        source_commit="c" * 40,
        archive_sha256="d" * 64,
    )
    service._desired_state = lambda selector=None, *, exact_release=False: (
        (None, "ReleaseError: published release selector must be an immutable version")
        if exact_release
        else (mutated, None)
    )
    journal = bootstrap_module._journal_path(service.receipt_path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "prepared",
            "codex",
            prior_receipt_digest="e" * 64,
            target_identity="f" * 64,
        ),
    )
    adapter.calls.clear()

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert adapter.calls == ["detect", "install", "inspect", "probe"]
    updated = read_receipt(service.receipt_path)
    assert updated is not None and updated.release_version == "local-222222222222"
    assert not journal.exists()


def test_bootstrap_sync_preserves_declared_degradations_in_report_json(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract-declared Codex degradations must remain converged in JSON output."""
    declared = ("manifest-ops codex hook mode is degraded",)
    degraded_codex = HarnessResult(
        "codex",
        ResultState.DEGRADED,
        ("manifest-ops@manifest",),
        {"manifest-ops:hook:version-pin": "degraded"},
        errors=declared,
        declared_degradations=declared,
    )
    codex = FakeAdapter("codex", degraded_codex)
    service = service_factory({"codex": codex}, harnesses=("codex",))
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()
    payload = result.to_dict()

    assert result.state is ResultState.DEGRADED
    assert payload["harnesses"]["codex"]["state"] == "DEGRADED"
    assert payload["harnesses"]["codex"]["converged"] is True
