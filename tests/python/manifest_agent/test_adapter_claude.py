"""Claude Code marketplace adapter tests."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.claude import ClaudeAdapter
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    BundleContract,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    OwnedEntry,
    ResultState,
)
from manifest_agent.process import CommandRunner


class QueueRunner(CommandRunner):
    def __init__(self, results: Sequence[CommandResult]) -> None:
        self.results = list(results)
        self.log: list[list[str]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        del env
        self.log.append(list(argv))
        result = self.results.pop(0)
        return CommandResult(
            tuple(argv), result.returncode, result.stdout, result.stderr
        )


def command(
    *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> CommandResult:
    return CommandResult(("fixture",), returncode, stdout, stderr)


@pytest.fixture
def desired(tmp_path: Path) -> DesiredState:
    contracts = tuple(
        BundleContract(name, "0.2.0", "fixture", "fixture", None, None, None, None)
        for name in DOMAIN_BUNDLES
    )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source=str(tmp_path),
        release_root=tmp_path,
        repository_url="https://example.invalid/Manifest",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=contracts,
        selected_optional=frozenset(),
        requested_harnesses=("claude",),
    )


def installed_json(version: str = "0.2.0", *, extra: bool = False) -> str:
    rows = [
        {
            "id": f"{name}@manifest",
            "version": version,
            "scope": "user",
            "enabled": True,
        }
        for name in DOMAIN_BUNDLES
    ]
    if extra:
        rows.append(
            {
                "id": "adversarial-design-loop@manifest",
                "version": "0.1.0",
                "scope": "user",
                "enabled": True,
            }
        )
    return json.dumps(rows)


def test_detection_reports_absent_cli_explicitly() -> None:
    adapter = ClaudeAdapter(which=lambda _name: None)

    detection = adapter.detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "claude CLI not present"


def test_claude_installs_marketplace_and_nine_user_plugins(
    desired: DesiredState,
) -> None:
    runner = QueueRunner([command()] * 10 + [command(stdout=installed_json())])
    adapter = ClaudeAdapter(runner=runner, which=lambda name: name)

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "claude",
        "plugin",
        "marketplace",
        "add",
        desired.source,
        "--scope",
        "user",
    ]
    assert [row for row in runner.log if row[1:3] == ["plugin", "install"]] == [
        ["claude", "plugin", "install", f"{name}@manifest", "--scope", "user"]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-1] == ["claude", "plugin", "list", "--json"]
    assert result.installed_plugin_ids == tuple(
        f"{name}@manifest" for name in DOMAIN_BUNDLES
    )


def test_already_present_is_idempotent_only_after_selected_version_inspection(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(returncode=1, stderr="already present")] * 10
        + [command(stdout=installed_json())]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.READY
    assert result.errors == ()
    assert runner.log[-1] == ["claude", "plugin", "list", "--json"]


def test_inspect_reports_selected_version_drift(desired: DesiredState) -> None:
    runner = QueueRunner([command(stdout=installed_json("0.1.0"))])

    result = ClaudeAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in result.errors[0]


def test_install_failure_is_redacted_when_inspection_cannot_confirm_state(
    desired: DesiredState,
) -> None:
    rows = json.loads(installed_json())
    rows.pop()
    runner = QueueRunner(
        [command(returncode=1, stderr="--token native-secret rejected")]
        + [command()] * 9
        + [command(stdout=json.dumps(rows))]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)


def test_non_idempotent_failure_propagates_even_when_state_is_already_ready(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(returncode=1, stderr="authentication failed")]
        + [command()] * 9
        + [command(stdout=installed_json())]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "authentication failed" in result.errors[0]


def test_uninstall_removes_only_receipt_plugins_and_retains_shared_marketplace() -> (
    None
):
    runner = QueueRunner(
        [
            command(),
            command(
                stdout=json.dumps(
                    [
                        {
                            "id": "adversarial-design-loop@manifest",
                            "version": "0.1.0",
                            "scope": "user",
                        }
                    ]
                )
            ),
        ]
    )
    receipt = HarnessReceipt(
        harness="claude",
        adapter_version="1",
        native_version="2",
        plugin_ids=("manifest-docs@manifest",),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log == [
        ["claude", "plugin", "uninstall", "manifest-docs@manifest"],
        ["claude", "plugin", "list", "--json"],
    ]
    assert "unowned plugin" in result.warnings[0]


def test_uninstall_removes_owned_marketplace_when_no_plugins_reference_it() -> None:
    runner = QueueRunner([command(), command(stdout="[]"), command()])
    receipt = HarnessReceipt(
        harness="claude",
        adapter_version="1",
        native_version="2",
        plugin_ids=("manifest-docs",),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-1] == [
        "claude",
        "plugin",
        "marketplace",
        "remove",
        "manifest",
    ]


@pytest.mark.native
def test_native_claude_uses_an_isolated_home(tmp_path: Path) -> None:
    executable = shutil.which("claude")
    if executable is None:
        pytest.skip("claude CLI not present")
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    env = {
        "HOME": str(isolated_home),
        "CLAUDE_CONFIG_DIR": str(isolated_home / ".claude"),
        "PATH": os.environ["PATH"],
    }
    repository = Path(__file__).parents[3]

    added = CommandRunner().run(
        (
            executable,
            "plugin",
            "marketplace",
            "add",
            str(repository),
            "--scope",
            "user",
        ),
        env=env,
    )
    result = CommandRunner().run(
        (executable, "plugin", "marketplace", "list", "--json"), env=env
    )

    assert added.returncode == 0, added.stderr
    assert result.returncode == 0, result.stderr
    marketplaces = json.loads(result.stdout)
    assert any(row["name"] == "manifest" for row in marketplaces)
