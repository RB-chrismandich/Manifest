"""One-writer migration tests with only temporary harness homes."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path

from manifest_agent.adapters.base import Detection
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.migration import MigrationService
from manifest_agent.models import HarnessResult, ResultState
from manifest_agent.paths import xdg_paths
from manifest_agent.service import ManifestService
from manifest_agent.state import read_receipt
from tests.python.manifest_agent.test_service_install import (
    fake_contracts,
    fake_release,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "legacy_homes"


class MigrationAdapter:
    adapter_version = "test"

    def __init__(self, event_log: list[str]) -> None:
        self.name = "claude"
        self.event_log = event_log
        self.verify_result = HarnessResult(
            "claude", ResultState.READY, DOMAIN_BUNDLES, {"plugins": "verified"}
        )

    def detect(self):
        return Detection(True, "fake", "1.0")

    def shadow_install(self, desired, home):
        del desired, home
        return HarnessResult("claude", ResultState.READY, DOMAIN_BUNDLES, {})

    def shadow_inspect(self, desired, home):
        del desired, home
        return HarnessResult("claude", ResultState.READY, DOMAIN_BUNDLES, {})

    def install(self, desired):
        del desired
        return HarnessResult("claude", ResultState.READY, DOMAIN_BUNDLES, {})

    def inspect(self, desired):
        del desired
        return self.verify_result

    def uninstall(self, receipt):
        del receipt
        return HarnessResult("claude", ResultState.READY, (), {})


@contextmanager
def fake_lock(path=None):
    yield path


def _service(tmp_path: Path, adapter: MigrationAdapter):
    release = fake_release(tmp_path)
    return ManifestService(
        source=release.release_root,
        harnesses=("claude",),
        adapters={"claude": adapter},
        receipt_path=tmp_path / "state" / "installation.json",
        release_resolver=lambda selector: release,
        contract_loader=lambda root: fake_contracts(),
        capability_planner=lambda contracts, selected: object(),
        lock_factory=fake_lock,
    )


def _legacy_home(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    manifest = home / ".manifest" / "skills"
    shutil.copytree(FIXTURES / "bootstrap-managed" / "manifest-skills", manifest)
    link = home / ".claude" / "skills"
    link.parent.mkdir(parents=True)
    link.symlink_to(manifest)
    return home, link


def test_migration_never_exposes_zero_or_two_writers(tmp_path: Path):
    events: list[str] = []
    home, _link = _legacy_home(tmp_path)
    adapter = MigrationAdapter(events)
    service = _service(tmp_path, adapter)
    migration = MigrationService.from_manifest_service(
        service, paths=xdg_paths({"HOME": str(home)}), home=home, event_log=events
    )

    report = migration.migrate(service._desired_state()[0])

    assert report.state is ResultState.READY
    assert events == [
        "snapshot-legacy",
        "shadow-install",
        "shadow-verify",
        "disable-legacy",
        "native-install",
        "native-verify",
        "commit-receipt",
    ]
    assert read_receipt(service.receipt_path) is not None


def test_failed_native_verify_restores_legacy_writer(tmp_path: Path):
    events: list[str] = []
    home, link = _legacy_home(tmp_path)
    adapter = MigrationAdapter(events)
    adapter.verify_result = HarnessResult(
        "claude", ResultState.BLOCKED, (), {}, errors=("native verify failed",)
    )
    service = _service(tmp_path, adapter)
    migration = MigrationService.from_manifest_service(
        service, paths=xdg_paths({"HOME": str(home)}), home=home, event_log=events
    )

    report = migration.migrate(service._desired_state()[0])

    assert report.state is ResultState.BLOCKED
    assert link.is_symlink()
    assert not service.receipt_path.exists()


def test_migration_preserves_unowned_settings(tmp_path: Path):
    events: list[str] = []
    home, _link = _legacy_home(tmp_path)
    settings = home / ".claude" / "settings.local.json"
    shutil.copy2(FIXTURES / "mixed-user-state" / "settings.local.json", settings)
    before = settings.read_bytes()
    adapter = MigrationAdapter(events)
    service = _service(tmp_path, adapter)
    migration = MigrationService.from_manifest_service(
        service, paths=xdg_paths({"HOME": str(home)}), home=home, event_log=events
    )

    report = migration.migrate(service._desired_state()[0])

    assert report.state is ResultState.READY
    assert settings.read_bytes() == before


def test_completed_migration_is_idempotent(tmp_path: Path):
    events: list[str] = []
    home, _link = _legacy_home(tmp_path)
    service = _service(tmp_path, MigrationAdapter(events))
    migration = MigrationService.from_manifest_service(
        service, paths=xdg_paths({"HOME": str(home)}), home=home, event_log=events
    )
    desired, error = service._desired_state()
    assert error is None and desired is not None
    assert migration.migrate(desired).state is ResultState.READY
    events.clear()

    assert migration.migrate(desired).state is ResultState.READY
    assert events == []


def test_partial_migration_resumes_after_rechecking_shadow(tmp_path: Path):
    events: list[str] = []
    home, _link = _legacy_home(tmp_path)
    service = _service(tmp_path, MigrationAdapter(events))
    migration = MigrationService.from_manifest_service(
        service, paths=xdg_paths({"HOME": str(home)}), home=home, event_log=events
    )
    desired, error = service._desired_state()
    assert error is None and desired is not None
    state = migration._load_or_snapshot(("claude",))
    state["harnesses"]["claude"]["phase"] = "shadow-installed"
    migration._write_state(state)
    events.clear()

    assert migration.migrate(desired).state is ResultState.READY
    assert events == [
        "shadow-verify",
        "disable-legacy",
        "native-install",
        "native-verify",
        "commit-receipt",
    ]
    backup = Path(state["backup"])
    assert (backup / "recovery.json").is_file()
    assert (backup / "restore.py").stat().st_mode & 0o777 == 0o700
