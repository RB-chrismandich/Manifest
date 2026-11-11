"""Multi-harness transactions: prepare-all, resume, and compensation."""

import subprocess
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
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import ResultState
from manifest_agent.release import resolve_release
from manifest_agent.state import read_receipt, receipt_digest
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    ReleasePin,
    bump_release,
    legacy_skill_home,
    three_harness_service,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


def test_release_change_converges_every_owned_harness_before_cutover(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    bump_release(service)
    service.harnesses = ("codex",)
    claude.calls.clear()
    codex.calls.clear()
    home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY
    # Inspect-first reconciliation avoids mutating an already-ready participant.
    assert claude.calls == ["prepare", "detect", "verify", "inspect"]
    assert codex.calls == ["detect", "install", "inspect"]
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert receipt.source_commit == "c" * 40
    assert not (home / ".codex/skills").is_symlink()


def test_release_change_blocks_before_codex_when_owned_harness_is_unavailable(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    bump_release(service)
    service.harnesses = ("codex",)
    claude.detection.present = False
    claude.calls.clear()
    codex.calls.clear()
    _home, legacy = legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert "unavailable: claude" in result.errors[0]
    assert codex.calls == ["detect"]
    assert legacy.is_symlink()


def test_cross_harness_transaction_prepares_every_participant_before_mutation(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, cursor, _codex = three_harness_service(service_factory)
    bump_release(service)
    service.harnesses = ("codex",)
    claude.inspection = harness_result("claude", ResultState.DRIFTED)
    cursor.inspection = harness_result("cursor", ResultState.DRIFTED)
    events: list[str] = []
    prepared: list[ReconciliationSaga] = []
    real_write = bootstrap_module._write_journal

    def record_write(path, saga):
        if saga.phase == "harness-prepared":
            prepared.append(saga)
            events.append("prepared")
        real_write(path, saga)

    def wrap_install(adapter, name):
        original = adapter.install

        def install(desired):
            events.append(f"mutate:{name}")
            result = original(desired)
            adapter.inspection = result
            return result

        adapter.install = install

    wrap_install(claude, "claude")
    wrap_install(cursor, "cursor")
    monkeypatch.setattr(bootstrap_module, "_write_journal", record_write)
    _home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY
    assert events[0] == "prepared"
    assert {item.harness for item in prepared[0].harness_mutations} == {
        "claude",
        "cursor",
    }
    assert all(item.phase == "prepared" for item in prepared[0].harness_mutations)


def test_cross_harness_transaction_resumes_after_partial_failure(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, cursor, _codex = three_harness_service(service_factory)
    bump_release(service)
    service.harnesses = ("codex",)
    claude.inspection = harness_result("claude", ResultState.DRIFTED)
    cursor.inspection = harness_result("cursor", ResultState.DRIFTED)
    cursor.result = harness_result(
        "cursor", ResultState.BLOCKED, errors=("injected failure",)
    )
    original_claude_install = claude.install

    def converge_claude(desired):
        result = original_claude_install(desired)
        claude.inspection = result
        return result

    claude.install = converge_claude
    _home, legacy = legacy_skill_home(tmp_path, monkeypatch)

    first = service.bootstrap_sync()

    assert first.state is ResultState.BLOCKED
    journal = _read_journal(
        service.receipt_path.with_name(
            f".{service.receipt_path.name}.bootstrap-sync.json"
        )
    )
    assert journal is None
    assert legacy.is_symlink()

    claude.inspection = harness_result("claude")
    cursor.result = harness_result("cursor")
    cursor.inspection = harness_result("cursor")
    second = service.bootstrap_sync()

    assert second.state is ResultState.READY
    assert claude.calls.count("prepare") == 2
    assert cursor.calls.count("prepare") == 2


def test_codex_failure_compensates_all_verified_owned_harnesses(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, cursor, codex = three_harness_service(service_factory)
    bump_release(service)
    service.harnesses = ("codex",)
    for adapter in (claude, cursor):
        adapter.inspection = harness_result(adapter.name, ResultState.DRIFTED)
        original_install = adapter.install

        def converge(desired, current=adapter, install=original_install):
            result = install(desired)
            current.inspection = result
            return result

        adapter.install = converge
    codex.result = harness_result(
        "codex", ResultState.BLOCKED, errors=("injected Codex failure",)
    )
    _home, legacy = legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert claude.calls.count("rollback") == 1
    assert cursor.calls.count("rollback") == 1
    saga = _read_journal(
        service.receipt_path.with_name(
            f".{service.receipt_path.name}.bootstrap-sync.json"
        )
    )
    assert saga is None
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None and receipt.source_commit == "a" * 40
    assert legacy.is_symlink()


def test_cross_harness_changed_target_compensates_before_accepting_new_target(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, cursor, _codex = three_harness_service(service_factory)
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    pin = ReleasePin(service, previous.release_version)
    old_release = pin.old_release
    service.harnesses = ("codex",)
    desired, error = service._desired_state()
    assert error is None and desired is not None
    prior_desired, error = service._desired_state(
        previous.release_version, exact_release=True
    )
    assert error is None and prior_desired is not None
    mutations = tuple(
        HarnessMutationCheckpoint(
            name,
            "applied" if name == "cursor" else "prepared",
            _serialize_handle(
                service.adapters[name].prepare_reconcile(
                    previous.harnesses[name], prior_desired, desired
                )
            ),
        )
        for name in ("claude", "cursor")
    )
    journal = service.receipt_path.with_name(
        f".{service.receipt_path.name}.bootstrap-sync.json"
    )
    _write_journal(
        journal,
        ReconciliationSaga(
            "harness-convergence",
            "codex",
            harness_mutations=mutations,
            prior_receipt_digest=receipt_digest(previous),
            target_identity=bootstrap_module._target_identity(desired),
        ),
    )
    rollback_releases: list[str] = []
    original_rollback = cursor.rollback_reconcile

    def record_rollback(handle, prior):
        rollback_releases.append(prior.release_version)
        return original_rollback(handle, prior)

    cursor.rollback_reconcile = record_rollback
    claude.calls.clear()
    cursor.calls.clear()
    _home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    pin.target = pin.release("3.0.0", "e" * 40, "f" * 64)
    result = service.bootstrap_sync()

    assert result.state is ResultState.READY
    assert rollback_releases == [old_release.version]
    assert cursor.calls.index("rollback") < cursor.calls.index("prepare")


def test_changed_target_rebinds_empty_preparation_journal(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    pin = ReleasePin(service, previous.release_version)
    service.harnesses = ("codex",)
    _home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    first_target, error = service._desired_state()
    assert error is None and first_target is not None
    first_identity = bootstrap_module._target_identity(first_target)
    journal = service.receipt_path.with_name(
        f".{service.receipt_path.name}.bootstrap-sync.json"
    )
    real_write = bootstrap_module._write_journal
    crashed = False

    def crash_after_empty_prepare(path, saga):
        nonlocal crashed
        real_write(path, saga)
        if (
            not crashed
            and saga.phase == "prepared"
            and saga.target_identity == first_identity
            and not saga.repairs
            and saga.plugin_change is None
            and saga.cutover_entry is None
            and not saga.harness_mutations
            and not saga.target_receipt_digest
        ):
            crashed = True
            raise SystemExit("injected empty-journal crash")

    monkeypatch.setattr(bootstrap_module, "_write_journal", crash_after_empty_prepare)

    with pytest.raises(SystemExit, match="empty-journal crash"):
        service.bootstrap_sync()

    stale = _read_journal(journal)
    assert stale is not None and stale.target_identity == first_identity
    pin.target = pin.release("3.0.0", "e" * 40, "f" * 64)

    restarted = service.bootstrap_sync()

    assert restarted.state is ResultState.READY
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None and receipt.release_version == "3.0.0"
    assert not journal.exists()


def _local_git_checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout"
    (repo / "tools").mkdir(parents=True)
    for name in DOMAIN_BUNDLES:
        bundle = repo / "plugins" / name
        bundle.mkdir(parents=True)
        (bundle / "payload.txt").write_text(f"{name}\n", encoding="utf-8")
    (repo / "tools" / "generate_plugin_views.py").write_text(
        "import sys\nraise SystemExit(0 if '--check' in sys.argv else 2)\n",
        encoding="utf-8",
    )
    for cmd in (
        ("init",),
        ("config", "user.email", "manifest@example.invalid"),
        ("config", "user.name", "Manifest Test"),
        ("add", "."),
        ("commit", "-m", "initial"),
    ):
        subprocess.run(("git", "-C", str(repo), *cmd), check=True, capture_output=True)
    return repo


def _installed_local_service(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    repo = _local_git_checkout(tmp_path)
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.source = repo
    service.release_resolver = resolve_release
    assert service.install().state is ResultState.READY
    return service, repo, claude, codex


def test_local_directory_checkout_mutation_runs_forward_only_bootstrap_sync(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, repo, claude, codex = _installed_local_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = read_receipt(service.receipt_path)
    assert previous is not None and previous.release_version.startswith("local-")
    assert previous.source_dirty is False
    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "mutated checkout\n", encoding="utf-8"
    )
    claude.inspection = harness_result("claude", ResultState.DRIFTED)
    original_claude_install = claude.install

    def converge_claude(desired):
        installed = original_claude_install(desired)
        claude.inspection = installed
        return installed

    claude.install = converge_claude
    claude.calls.clear()
    codex.calls.clear()
    service.harnesses = ("codex",)
    home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert "prepare" not in claude.calls
    assert claude.calls == ["detect", "inspect", "install", "inspect"]
    assert codex.calls == ["detect", "install", "inspect"]
    updated = read_receipt(service.receipt_path)
    assert updated is not None and updated.source_dirty is True
    assert updated.release_version == previous.release_version
    assert updated.archive_sha256 != previous.archive_sha256
    assert updated.bundle_checksums != previous.bundle_checksums
    assert not (home / ".codex/skills").is_symlink()
    assert not bootstrap_module._journal_path(service.receipt_path).exists()


def test_unresolvable_prior_release_remains_fail_closed_after_recorded_mutation(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, repo, claude, codex = _installed_local_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    prior_desired, error = service._desired_state()
    assert error is None and prior_desired is not None

    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "mutated after crash\n", encoding="utf-8"
    )
    desired, error = service._desired_state()
    assert error is None and desired is not None
    handle = claude.prepare_reconcile(
        previous.harnesses["claude"], prior_desired, desired
    )
    journal = bootstrap_module._journal_path(service.receipt_path)
    recorded_saga = ReconciliationSaga(
        "harness-convergence",
        "codex",
        harness_mutations=(
            HarnessMutationCheckpoint("claude", "applied", _serialize_handle(handle)),
        ),
        prior_receipt_digest=receipt_digest(previous),
        target_identity=bootstrap_module._target_identity(desired),
    )
    _write_journal(journal, recorded_saga)
    journal_before = journal.read_text(encoding="utf-8")
    claude.calls.clear()
    codex.calls.clear()
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
