"""Multi-harness transactions: prepare-all, resume, and compensation."""

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
    ResultState,
)
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
    service, claude, gemini, _codex = three_harness_service(service_factory)
    bump_release(service)
    service.harnesses = ("codex",)
    claude.inspection = harness_result("claude", ResultState.DRIFTED)
    gemini.inspection = harness_result("gemini", ResultState.DRIFTED)
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
    wrap_install(gemini, "gemini")
    monkeypatch.setattr(bootstrap_module, "_write_journal", record_write)
    _home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY
    assert events[0] == "prepared"
    assert {item.harness for item in prepared[0].harness_mutations} == {
        "claude",
        "gemini",
    }
    assert all(item.phase == "prepared" for item in prepared[0].harness_mutations)


def test_cross_harness_transaction_resumes_after_partial_failure(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, gemini, _codex = three_harness_service(service_factory)
    bump_release(service)
    service.harnesses = ("codex",)
    claude.inspection = harness_result("claude", ResultState.DRIFTED)
    gemini.inspection = harness_result("gemini", ResultState.DRIFTED)
    gemini.result = harness_result(
        "gemini", ResultState.BLOCKED, errors=("injected failure",)
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
    gemini.result = harness_result("gemini")
    gemini.inspection = harness_result("gemini")
    second = service.bootstrap_sync()

    assert second.state is ResultState.READY
    assert claude.calls.count("prepare") == 2
    assert gemini.calls.count("prepare") == 2


def test_codex_failure_compensates_all_verified_owned_harnesses(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, claude, gemini, codex = three_harness_service(service_factory)
    bump_release(service)
    service.harnesses = ("codex",)
    for adapter in (claude, gemini):
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
    assert gemini.calls.count("rollback") == 1
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
    service, claude, gemini, _codex = three_harness_service(service_factory)
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
            "applied" if name == "gemini" else "prepared",
            _serialize_handle(
                service.adapters[name].prepare_reconcile(
                    previous.harnesses[name], prior_desired, desired
                )
            ),
        )
        for name in ("claude", "gemini")
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
    original_rollback = gemini.rollback_reconcile

    def record_rollback(handle, prior):
        rollback_releases.append(prior.release_version)
        return original_rollback(handle, prior)

    gemini.rollback_reconcile = record_rollback
    claude.calls.clear()
    gemini.calls.clear()
    _home, _legacy = legacy_skill_home(tmp_path, monkeypatch)

    pin.target = pin.release("3.0.0", "e" * 40, "f" * 64)
    result = service.bootstrap_sync()

    assert result.state is ResultState.READY
    assert rollback_releases == [old_release.version]
    assert gemini.calls.index("rollback") < gemini.calls.index("prepare")


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
