"""Manifest update repair and foreign-conflict refusal regression tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import manifest_agent.cli as cli_module
import tests.python.manifest_agent._codex_adapter_test_support as codex_support
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import DesiredState, HarnessResult, ResultState
from manifest_agent.release import ResolvedRelease
from manifest_agent.service import ManifestService
from manifest_agent.state import read_receipt
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    command,
    installed_json,
    marketplace_add_json,
    marketplace_json,
    mcp_list_json,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    fake_lock,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path) -> Any:
    """Return an isolated ManifestService builder rooted in tmp_path."""
    return make_service_factory(tmp_path)


def test_cli_update_repairs_recoverable_blocked_harness(
    service_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`manifest update` reinstalls recoverable BLOCKED owned harnesses."""

    class _HealingAdapter(FakeAdapter):
        heal = False

        def install(self, desired: Any) -> HarnessResult:
            if self.heal:
                self.result = harness_result(self.name)
                self.inspection = self.result
            return super().install(desired)

    blocked = harness_result(
        "codex",
        ResultState.BLOCKED,
        errors=("missing required plugin: manifest-workspace@manifest",),
        plugin_ids=(),
    )
    codex = _HealingAdapter("codex", blocked)
    service = service_factory({"codex": codex}, harnesses=("codex",))
    assert service.install().state is ResultState.BLOCKED
    codex.calls.clear()
    codex.heal = True
    monkeypatch.setattr(cli_module, "_service", lambda **_options: service)

    result = CliRunner().invoke(cli_module.cli, ["update"])

    assert result.exit_code == 0
    assert codex.calls == ["detect", "inspect", "install", "inspect"]
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None and receipt.harnesses["codex"].verified is True


@pytest.mark.parametrize(
    ("harness", "error"),
    [
        (
            "antigravity",
            "plugin manifest-workspace expected source antigravity, found foreign-src",
        ),
        ("claude", "manifest marketplace is not a native directory source"),
        ("devin", "Devin global_rules.md contains unowned user content"),
    ],
)
def test_update_skips_explicit_foreign_conflict_blocked_harness(
    service_factory: Any, harness: str, error: str
) -> None:
    """Explicit foreign-conflict BLOCKED diagnostics skip reinstall mutations."""
    adapter = FakeAdapter(harness, harness_result(harness))
    service = service_factory({harness: adapter}, harnesses=(harness,))
    service.install()
    before = service.receipt_path.read_bytes()
    adapter.calls.clear()
    adapter.inspection = harness_result(harness, ResultState.BLOCKED, errors=(error,))

    report = service.reconcile(apply=True)

    assert report.state is ResultState.BLOCKED
    assert error in report.harnesses[harness].errors
    assert adapter.calls == ["detect", "inspect"]
    assert service.receipt_path.read_bytes() == before


def test_update_skips_conflicting_only_capability_blocker(service_factory: Any) -> None:
    """Conflicting-only required capability blockers do not reinstall clean plugins."""
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"codex": codex}, harnesses=("codex",))
    service.install()
    before = service.receipt_path.read_bytes()
    codex.calls.clear()
    codex.inspection = HarnessResult(
        "codex",
        ResultState.BLOCKED,
        DOMAIN_BUNDLES,
        {"manifest-workspace:mcp:context7": "conflicting"},
        errors=("Codex MCP server context7 is disabled",),
    )

    report = service.reconcile(apply=True)

    assert report.state is ResultState.BLOCKED
    assert codex.calls == ["detect", "inspect"]
    assert service.receipt_path.read_bytes() == before


def _codex_service(
    desired: DesiredState, state_home: Path, codex: CodexAdapter
) -> ManifestService:
    resolved = ResolvedRelease(
        desired.release_version,
        desired.source_commit,
        desired.source,
        desired.marketplace_source,
        desired.release_root,
        desired.repository_url,
        desired.source_dirty,
        desired.archive_sha256,
    )
    return ManifestService(
        source=desired.release_root,
        harnesses=("codex",),
        adapters={"codex": codex},
        receipt_path=state_home / "manifest" / "installation.json",
        release_resolver=lambda _selector: resolved,
        contract_loader=lambda _root: desired.contracts,
        addon_contract_loader=lambda _root: desired.addon_contracts,
        capability_planner=lambda _contracts, _selected: object(),
        lock_factory=fake_lock,
    )


def _foreign_cache_runner(desired: DesiredState, cache_link: Path) -> QueueRunner:
    root = desired.release_root
    stale_payload = json.loads(installed_json(desired))
    stale_payload["installed"][0].update(version="0.1.0", installedPath=str(cache_link))
    stale_json, mp_json = json.dumps(stale_payload), marketplace_json(str(root), root)
    ok_inspect = [
        command(stdout=mp_json),
        command(stdout=installed_json(desired)),
        command(stdout=mcp_list_json()),
    ]
    stale_inspect = [
        command(stdout=mp_json),
        command(stdout=stale_json),
        command(stdout=mcp_list_json()),
    ]
    return QueueRunner(
        [
            command(stdout="0.153.4\n"),
            command(stdout=marketplace_add_json(root)),
            command(stdout=mp_json),
            command(stdout=installed_json(desired)),
            *ok_inspect,
            *ok_inspect,
            command(stdout="0.153.4\n"),
            *stale_inspect,
            command(stdout=marketplace_add_json(root, already_added=True)),
            command(stdout=mp_json),
            command(stdout=stale_json),
            *stale_inspect,
            *stale_inspect,
        ]
    )


def test_update_reinstall_path_refuses_foreign_codex_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reinstall-path backup validation refuses symlinked foreign plugin caches."""
    desired = codex_support.desired.__wrapped__(tmp_path / "release")
    state_home = tmp_path / "xdg-state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    codex_home, foreign_dir = tmp_path / "codex-home", tmp_path / "foreign-cache"
    foreign_dir.mkdir(parents=True)
    (foreign_dir / "payload.txt").write_text("foreign content\n", encoding="utf-8")
    cache_link = codex_home / f"plugins/cache/manifest/{DOMAIN_BUNDLES[0]}/0.2.0"
    cache_link.parent.mkdir(parents=True)
    cache_link.symlink_to(foreign_dir)

    runner = _foreign_cache_runner(desired, cache_link)
    codex = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={
            "CODEX_HOME": str(codex_home),
            "HOME": str(tmp_path / "home"),
            "XDG_STATE_HOME": str(state_home),
        },
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    )
    service = _codex_service(desired, state_home, codex)
    assert service.install().state is ResultState.READY
    runner.log.clear()

    report = service.reconcile(apply=True)

    assert report.state is ResultState.BLOCKED
    assert "not a regular directory" in " ".join(report.harnesses["codex"].errors)
    assert not any(argv[:3] == ["codex", "plugin", "remove"] for argv in runner.log)
    assert cache_link.is_symlink()
    assert (foreign_dir / "payload.txt").read_text(encoding="utf-8") == (
        "foreign content\n"
    )
