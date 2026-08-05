"""Install service orchestration tests with isolated adapter fakes."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import manifest_agent.service as service_module
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    BundleContract,
    CommandResult,
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import owned_capability_entry
from manifest_agent.release import ResolvedRelease
from manifest_agent.service_state import bundle_checksums
from manifest_agent.state import (
    RetiredGraphifyTransaction,
    read_receipt,
    read_retired_graphify_transaction,
    retired_graphify_transaction_path,
    write_receipt_atomic,
    write_retired_graphify_transaction_atomic,
)


@dataclass
class FakeDetection:
    present: bool = True
    executable: str | None = "fake"
    version: str | None = "1.0.0"
    reason: str | None = None


class FakeAdapter:
    adapter_version = "1"

    def __init__(self, name: str, result: HarnessResult) -> None:
        self.name = name
        self.result = result
        self.inspection = result
        self.detection = FakeDetection()
        self.calls: list[str] = []
        self.uninstall_receipts = []
        self.snapshot_files: tuple[Path, ...] = ()

    def detect(self):
        self.calls.append("detect")
        return self.detection

    def install(self, desired):
        del desired
        self.calls.append("install")
        return self.result

    def inspect(self, desired):
        del desired
        self.calls.append("inspect")
        return self.inspection

    def uninstall(self, receipt):
        self.calls.append("uninstall")
        self.uninstall_receipts.append(receipt)
        return self.result

    def snapshot_paths(self, desired):
        del desired
        return self.snapshot_files


class RecordingRunner:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.returncode = returncode

    def run(self, argv, *, env=None) -> CommandResult:
        del env
        command = tuple(argv)
        self.calls.append(command)
        return CommandResult(command, self.returncode, "", "native cleanup failed")


def harness_result(
    name: str,
    state: ResultState = ResultState.READY,
    *,
    errors: tuple[str, ...] = (),
    plugin_ids: tuple[str, ...] | None = None,
    owned_entries: tuple[OwnedEntry, ...] = (),
) -> HarnessResult:
    return HarnessResult(
        name,
        state,
        plugin_ids if plugin_ids is not None else DOMAIN_BUNDLES,
        {"plugins.install": "verified"},
        errors=errors,
        owned_entries=owned_entries,
    )


def fake_contracts() -> tuple[BundleContract, ...]:
    return tuple(
        BundleContract(name, "1.0.0", name, "test", None, None, None, None)
        for name in DOMAIN_BUNDLES
    )


def fake_release(tmp_path: Path) -> ResolvedRelease:
    root = tmp_path / "release"
    for name in DOMAIN_BUNDLES:
        bundle = root / "plugins" / name
        bundle.mkdir(parents=True)
        (bundle / "payload.txt").write_text(name, encoding="utf-8")
    return ResolvedRelease(
        "1.0.0",
        "a" * 40,
        "test-release",
        MarketplaceSource(MarketplaceSourceKind.LOCAL, str(root), None),
        root,
        "https://example.invalid/Manifest",
        False,
        "b" * 64,
    )


@contextmanager
def fake_lock(path=None):
    yield path


def make_service_factory(tmp_path):
    from manifest_agent.service import ManifestService

    release = fake_release(tmp_path)

    def make(adapters, *, harnesses=("claude", "codex")):
        return ManifestService(
            source=release.release_root,
            harnesses=harnesses,
            adapters=adapters,
            receipt_path=tmp_path / "state" / "installation.json",
            release_resolver=lambda selector: release,
            contract_loader=lambda root: fake_contracts(),
            capability_planner=lambda contracts, selected: object(),
            lock_factory=fake_lock,
            runner=RecordingRunner(),
        )

    return make


@pytest.fixture
def service_factory(tmp_path):
    return make_service_factory(tmp_path)


def test_install_preserves_successful_harness_after_later_failure(
    service_factory,
):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter(
        "codex",
        harness_result("codex", ResultState.BLOCKED, errors=("native install failed",)),
    )
    service = service_factory({"claude": claude, "codex": codex})

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert report.harnesses["claude"].state is ResultState.READY
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert receipt.harnesses["claude"].verified is True
    assert receipt.harnesses["codex"].verified is False


def test_install_uses_exact_harness_order_and_inspects_after_each_install(
    service_factory,
):
    event_log: list[str] = []

    class OrderedAdapter(FakeAdapter):
        def install(self, desired):
            event_log.append(f"install:{self.name}")
            return super().install(desired)

        def inspect(self, desired):
            event_log.append(f"inspect:{self.name}")
            return super().inspect(desired)

    adapters = {
        name: OrderedAdapter(name, harness_result(name)) for name in ("codex", "claude")
    }
    service = service_factory(adapters, harnesses=("codex", "claude"))

    service.install()

    assert event_log == [
        "install:claude",
        "inspect:claude",
        "install:codex",
        "inspect:codex",
    ]


def test_default_detection_skips_missing_harnesses_with_notes(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    codex.detection = FakeDetection(False, None, None, "codex CLI not present")
    service = service_factory({"claude": claude, "codex": codex}, harnesses=())

    report = service.install()

    assert tuple(report.harnesses) == ("claude",)
    assert report.state is ResultState.READY
    assert report.notes == ("codex: codex CLI not present",)
    assert "install" not in codex.calls


def test_harness_all_blocks_when_any_cli_is_missing(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    codex.detection = FakeDetection(False, None, None, "codex CLI not present")
    service = service_factory({"claude": claude, "codex": codex}, harnesses=("all",))

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert report.harnesses["codex"].state is ResultState.BLOCKED
    assert "install" not in codex.calls


def test_install_snapshots_only_adapter_declared_files(service_factory, tmp_path):
    declared = tmp_path / "native-settings.json"
    undeclared = tmp_path / "foreign-settings.json"
    declared.write_text("owned-before", encoding="utf-8")
    undeclared.write_text("foreign", encoding="utf-8")
    claude = FakeAdapter("claude", harness_result("claude"))
    claude.snapshot_files = (declared,)
    service = service_factory({"claude": claude}, harnesses=("claude",))

    service.install()

    snapshots = tuple(service.snapshot_root.rglob("*.bak"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == "owned-before"
    assert all("foreign-settings" not in path.name for path in snapshots)


def test_targeted_install_preserves_unrequested_receipt_ownership(service_factory):
    codex_owned = OwnedEntry("plugin", "codex-owned", "manifest")
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex", owned_entries=(codex_owned,)))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    before = read_receipt(service.receipt_path)
    assert before is not None
    service.harnesses = ("claude",)
    claude.result = harness_result(
        "claude", owned_entries=(OwnedEntry("plugin", "claude-owned", "manifest"),)
    )

    report = service.install()

    assert report.state is ResultState.READY
    after = read_receipt(service.receipt_path)
    assert after is not None
    assert after.harnesses["codex"] == before.harnesses["codex"]
    assert after.harnesses["codex"].owned_entries == (codex_owned,)


def test_targeted_install_blocks_incompatible_existing_release(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    before = read_receipt(service.receipt_path)
    assert before is not None
    old_release = service.release_resolver(service.source)
    service.release_resolver = lambda selector: type(old_release)(
        "2.0.0",
        "c" * 40,
        "replacement",
        old_release.marketplace_source,
        old_release.release_root,
        old_release.repository_url,
        False,
        "d" * 64,
    )
    service.harnesses = ("claude",)
    claude.calls.clear()

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert "install" not in claude.calls
    assert read_receipt(service.receipt_path) == before


def _write_legacy_graphify_receipt(service, *, forged: bool = False) -> bytes:
    desired, error = service._desired_state()
    assert error is None
    assert desired is not None
    entry = owned_capability_entry(
        "executable",
        "graphify",
        key_path=service.receipt_path.parent / "ownership.key",
    )
    receipt = InstallationReceipt(
        1,
        "0.1.0",
        "0.1.0",
        "c" * 40,
        False,
        "d" * 64,
        {**bundle_checksums(desired), "manifest-graphify": "e" * 64},
        (),
        {
            "claude": HarnessReceipt(
                "claude",
                "1",
                "1",
                (*DOMAIN_BUNDLES[:3], "manifest-graphify", *DOMAIN_BUNDLES[3:]),
                (entry,),
                {"executable:graphify": "installed-by-manifest"},
                True,
            )
        },
    )
    write_receipt_atomic(service.receipt_path, receipt)
    if forged:
        document = json.loads(service.receipt_path.read_text(encoding="utf-8"))
        document["harnesses"]["claude"]["owned_entries"][0][
            "previous_checksum"
        ] = "forged"
        service.receipt_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return service.receipt_path.read_bytes()


def _upgraded_graphify_receipt(service) -> InstallationReceipt:
    legacy = read_receipt(service.receipt_path)
    assert legacy is not None
    desired, error = service._desired_state()
    assert error is None
    assert desired is not None
    return replace(
        legacy,
        release_version=desired.release_version,
        source_commit=desired.source_commit,
        source_dirty=desired.source_dirty,
        archive_sha256=desired.archive_sha256,
        bundle_checksums=bundle_checksums(desired),
        harnesses={
            name: service_module._without_retired_graphify(harness)
            for name, harness in legacy.harnesses.items()
        },
    )


def test_install_upgrades_a_signed_nine_bundle_receipt(service_factory) -> None:
    # Empty result inventory preserves the receipt's upgraded plugin IDs.
    claude = FakeAdapter("claude", harness_result("claude", plugin_ids=()))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    before = _write_legacy_graphify_receipt(service)

    report = service.install()

    assert report.state is ResultState.READY
    assert service.runner.calls == [("uv", "tool", "uninstall", "graphifyy")]
    after = read_receipt(service.receipt_path)
    assert after is not None
    assert before != service.receipt_path.read_bytes()
    assert set(after.bundle_checksums) == set(DOMAIN_BUNDLES)
    assert after.release_version == "1.0.0"
    assert after.source_commit == "a" * 40
    assert after.harnesses["claude"].plugin_ids == DOMAIN_BUNDLES
    assert "executable:graphify" not in after.harnesses["claude"].capabilities
    assert not any(
        entry.identifier == "graphify"
        for entry in after.harnesses["claude"].owned_entries
    )


def test_graphify_cleanup_failure_leaves_the_legacy_receipt_unchanged(
    service_factory,
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.runner.returncode = 1
    before = _write_legacy_graphify_receipt(service)

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert service.runner.calls == [("uv", "tool", "uninstall", "graphifyy")]
    assert service.receipt_path.read_bytes() == before
    assert "install" not in claude.calls


def test_graphify_receipt_write_failure_retries_without_second_native_cleanup(
    monkeypatch, service_factory
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    before = _write_legacy_graphify_receipt(service)
    original_write = service_module.write_receipt_atomic
    failed = False

    def fail_first_receipt_write(path, receipt):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("injected receipt write failure")
        original_write(path, receipt)

    monkeypatch.setattr(service_module, "write_receipt_atomic", fail_first_receipt_write)

    first = service.install()

    transaction_path = retired_graphify_transaction_path(service.receipt_path)
    transaction = read_retired_graphify_transaction(transaction_path)
    assert first.state is ResultState.BLOCKED
    assert service.receipt_path.read_bytes() == before
    assert service.runner.calls == [("uv", "tool", "uninstall", "graphifyy")]
    assert transaction is not None
    assert transaction.phase == "cleanup-complete"

    second = service.install()

    assert second.state is ResultState.READY
    assert service.runner.calls == [("uv", "tool", "uninstall", "graphifyy")]
    assert set(read_receipt(service.receipt_path).bundle_checksums) == set(DOMAIN_BUNDLES)
    assert not transaction_path.exists()


def test_corrupt_graphify_transaction_blocks_before_native_cleanup(
    service_factory,
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    before = _write_legacy_graphify_receipt(service)
    retired_graphify_transaction_path(service.receipt_path).write_text(
        "not valid JSON", encoding="utf-8"
    )

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert service.runner.calls == []
    assert service.receipt_path.read_bytes() == before
    assert "install" not in claude.calls


def test_mismatched_graphify_transaction_blocks_before_native_cleanup(
    service_factory,
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    before = _write_legacy_graphify_receipt(service)
    transaction_path = retired_graphify_transaction_path(service.receipt_path)
    write_retired_graphify_transaction_atomic(
        transaction_path,
        RetiredGraphifyTransaction(
            phase="cleanup-complete",
            legacy_receipt_digest="f" * 64,
            target_receipt=_upgraded_graphify_receipt(service),
        ),
    )

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert service.runner.calls == []
    assert service.receipt_path.read_bytes() == before
    assert "install" not in claude.calls


def test_unproven_graphify_receipt_never_invokes_cleanup(service_factory) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    before = _write_legacy_graphify_receipt(service, forged=True)

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert service.runner.calls == []
    assert service.receipt_path.read_bytes() == before
    assert "install" not in claude.calls


def test_graphify_upgrade_requires_the_current_canonical_bundle_inventory(
    service_factory,
) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    _write_legacy_graphify_receipt(service)
    legacy = read_receipt(service.receipt_path)
    assert legacy is not None
    corrupt_checksums = dict(legacy.bundle_checksums)
    corrupt_checksums[DOMAIN_BUNDLES[0]] = "f" * 64
    write_receipt_atomic(
        service.receipt_path,
        InstallationReceipt(
            legacy.schema_version,
            legacy.coordinator_version,
            legacy.release_version,
            legacy.source_commit,
            legacy.source_dirty,
            legacy.archive_sha256,
            corrupt_checksums,
            legacy.selected_optional,
            legacy.harnesses,
            legacy.migration_backup,
        ),
    )
    before = service.receipt_path.read_bytes()

    report = service.install()

    assert report.state is ResultState.BLOCKED
    assert service.runner.calls == []
    assert service.receipt_path.read_bytes() == before
    assert "install" not in claude.calls
