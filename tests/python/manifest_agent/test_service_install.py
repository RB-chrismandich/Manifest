"""Install service orchestration tests with isolated adapter fakes."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    BundleContract,
    HarnessResult,
    MarketplaceSource,
    MarketplaceSourceKind,
    OwnedEntry,
    ResultState,
)
from manifest_agent.release import ResolvedRelease
from manifest_agent.state import read_receipt


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
    def __init__(self) -> None:
        self.calls = []


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
