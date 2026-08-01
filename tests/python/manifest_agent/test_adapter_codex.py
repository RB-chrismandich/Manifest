"""Codex native marketplace adapter tests."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.codex import CodexAdapter
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
    *, returncode: int = 0, stdout: str = "{}", stderr: str = ""
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
        source="https://example.invalid/Manifest.git",
        release_root=tmp_path,
        repository_url="https://example.invalid/Manifest",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=contracts,
        selected_optional=frozenset(),
        requested_harnesses=("codex",),
    )


def installed_json(version: str = "0.2.0", *, extra: bool = False) -> str:
    rows = [
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
            "version": version,
            "installed": True,
            "enabled": True,
        }
        for name in DOMAIN_BUNDLES
    ]
    if extra:
        rows.append(
            {
                "pluginId": "adversarial-design-loop@manifest",
                "name": "adversarial-design-loop",
                "marketplaceName": "manifest",
                "version": "0.1.0",
                "installed": True,
                "enabled": True,
            }
        )
    return json.dumps({"installed": rows})


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = CodexAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "codex CLI not present"


def test_codex_pins_marketplace_ref_and_installs_nine_plugins(
    desired: DesiredState,
) -> None:
    runner = QueueRunner([command()] * 10 + [command(stdout=installed_json())])
    adapter = CodexAdapter(runner=runner, which=lambda name: name)

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "codex",
        "plugin",
        "marketplace",
        "add",
        desired.source,
        "--ref",
        desired.source_commit,
        "--json",
    ]
    assert [row for row in runner.log if row[1:3] == ["plugin", "add"]] == [
        ["codex", "plugin", "add", f"{name}@manifest", "--json"]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-1] == ["codex", "plugin", "list", "--json"]


def test_codex_requires_structured_mutation_output(desired: DesiredState) -> None:
    runner = QueueRunner(
        [command(stdout="installed successfully")]
        + [command()] * 9
        + [command(stdout=installed_json())]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "valid JSON" in " ".join(result.errors)


def test_codex_already_present_requires_selected_version_inspection(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(stdout='{"alreadyAdded": true}')]
        + [command(stdout='{"alreadyInstalled": true}')] * 9
        + [command(stdout=installed_json())]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.READY
    assert result.errors == ()


def test_codex_inspect_reports_selected_version_drift(desired: DesiredState) -> None:
    runner = QueueRunner([command(stdout=installed_json("0.1.0"))])

    result = CodexAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in result.errors[0]


def test_codex_uninstall_retains_marketplace_for_unowned_plugin() -> None:
    runner = QueueRunner([command(), command(stdout=installed_json(extra=True))])
    receipt = HarnessReceipt(
        harness="codex",
        adapter_version="1",
        native_version="0.146",
        plugin_ids=tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )
    # One response is reused for each native remove before the final list.
    runner.results = [command()] * len(DOMAIN_BUNDLES) + [
        command(
            stdout=json.dumps(
                {
                    "installed": [
                        {
                            "pluginId": "adversarial-design-loop@manifest",
                            "marketplaceName": "manifest",
                            "version": "0.1.0",
                            "installed": True,
                        }
                    ]
                }
            )
        )
    ]

    result = CodexAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert all(row[-1] == "--json" for row in runner.log[:9])
    assert not any(
        row[1:4] == ["plugin", "marketplace", "remove"] for row in runner.log
    )
    assert "unowned plugin" in result.warnings[0]


def test_codex_uninstall_removes_owned_marketplace_when_unreferenced() -> None:
    runner = QueueRunner([command(), command(stdout=installed_json())])
    runner.results = [
        command(),
        command(stdout=json.dumps({"installed": []})),
        command(),
    ]
    receipt = HarnessReceipt(
        harness="codex",
        adapter_version="1",
        native_version="0.146",
        plugin_ids=("manifest-docs",),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-1] == [
        "codex",
        "plugin",
        "marketplace",
        "remove",
        "manifest",
        "--json",
    ]


@pytest.mark.native
def test_native_codex_uses_an_isolated_home(tmp_path: Path) -> None:
    executable = shutil.which("codex")
    if executable is None:
        pytest.skip("codex CLI not present")
    isolated_home = tmp_path / "home"
    (isolated_home / ".codex").mkdir(parents=True)
    env = {
        "HOME": str(isolated_home),
        "CODEX_HOME": str(isolated_home / ".codex"),
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
            "--json",
        ),
        env=env,
    )
    result = CommandRunner().run(
        (executable, "plugin", "marketplace", "list", "--json"), env=env
    )

    assert added.returncode == 0, added.stderr
    assert result.returncode == 0, result.stderr
    marketplaces = json.loads(result.stdout)["marketplaces"]
    assert any(row["name"] == "manifest" for row in marketplaces)
