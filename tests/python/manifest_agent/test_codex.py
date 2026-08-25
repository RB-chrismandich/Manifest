"""Codex native marketplace adapter core tests."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.adapters.codex_native import plugin_rows
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
)
from manifest_agent.models import (
    CatalogPlugin,
    DesiredState,
    ResultState,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    command,
    installed_json,
    marketplace_add_json,
    marketplace_json,
    mcp_list_json,
    plugin_add_json,
    plugin_remove_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = CodexAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "codex CLI not present"


def test_codex_plugin_rows_derive_versioned_runtime_cache(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    source = tmp_path / "marketplace-source/manifest-workspace"
    document = {
        "installed": [
            {
                "pluginId": "manifest-workspace@manifest",
                "name": "manifest-workspace",
                "marketplaceName": "manifest",
                "version": "0.2.0",
                "enabled": True,
                "source": {"path": str(source)},
            }
        ]
    }

    rows, error = plugin_rows(json.dumps(document), {"CODEX_HOME": str(codex_home)})

    assert error is None
    assert rows[0]["source"]["path"] == str(source)
    assert rows[0]["installedPath"] == str(
        codex_home / "plugins/cache/manifest/manifest-workspace/0.2.0"
    )


def test_codex_local_release_omits_ref_and_installs_canonical_plugins(
    desired: DesiredState,
) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            marketplace,
            command(stdout=json.dumps({"installed": []})),
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES
            ],
            marketplace,
            command(stdout=installed_json(desired)),
            command(stdout=mcp_list_json()),
        ]
    )
    adapter = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    )

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "codex",
        "plugin",
        "marketplace",
        "add",
        desired.marketplace_source.source,
        "--json",
    ]
    assert [row for row in runner.log if row[1:3] == ["plugin", "add"]] == [
        ["codex", "plugin", "add", f"{name}@manifest", "--json"]
        for name in DOMAIN_BUNDLES
    ]
    # inspect() ends by observing what Codex serves, so it does not re-add a
    # registered MCP server (test_codex_mcp_inventory.py).
    assert runner.log[-2] == ["codex", "plugin", "list", "--json"]
    assert runner.log[-1] == ["codex", "mcp", "list", "--json"]
    assert result.capabilities["manifest-workspace:skill:help"] == "verified"
    assert result.capabilities["manifest-workspace:mcp:context7"] == "verified"


def test_codex_requires_structured_mutation_output(desired: DesiredState) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner([command(stdout="installed successfully"), marketplace])

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "valid JSON" in " ".join(result.errors)
    assert not any(row[1:3] == ["plugin", "add"] for row in runner.log)


def test_codex_already_present_requires_selected_version_inspection(
    desired: DesiredState,
) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_add_json(
                    desired.marketplace_source.source, already_added=True
                )
            ),
            marketplace,
            command(stdout=installed_json(desired)),
            marketplace,
            command(stdout=installed_json(desired)),
            command(stdout=mcp_list_json()),
        ]
    )

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(desired)

    assert result.state is ResultState.READY
    assert result.errors == ()
    assert not any(row[1:3] == ["plugin", "add"] for row in runner.log)


def test_codex_marketplace_collision_blocks_before_plugin_install(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_add_json(
                    desired.marketplace_source.source, already_added=True
                )
            ),
            command(stdout=marketplace_json("/different/source", "/different/source")),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "marketplace source mismatch" in " ".join(result.errors)
    assert not any(row[1:3] == ["plugin", "add"] for row in runner.log)


def test_codex_plugin_add_requires_exact_native_identity(
    desired: DesiredState,
) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            marketplace,
            command(stdout=json.dumps({"installed": []})),
            command(stdout="{}"),
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES[1:]
            ],
            marketplace,
            command(stdout=installed_json(desired)),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "did not confirm manifest-code-quality@manifest" in result.errors[0]


def test_codex_repairs_stale_plugin_only_after_private_backup(
    desired: DesiredState, tmp_path: Path
) -> None:
    stale_name = DOMAIN_BUNDLES[0]
    stale_path = desired.bundle_path(stale_name)
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired, "0.1.0", names=(stale_name,))),
            command(stdout=plugin_remove_json(stale_name)),
            command(stdout=plugin_add_json(desired, stale_name)),
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES[1:]
            ],
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired)),
            command(stdout=mcp_list_json()),
        ]
    )
    adapter = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"HOME": str(tmp_path / "home")},
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    )

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert runner.log[3:5] == [
        ["codex", "plugin", "remove", f"{stale_name}@manifest", "--json"],
        ["codex", "plugin", "add", f"{stale_name}@manifest", "--json"],
    ]
    archives = list(
        (tmp_path / "home/.local/state/manifest/codex-plugin-backups").glob("*.tar")
    )
    assert len(archives) == 1
    assert archives[0].stat().st_mode & 0o777 == 0o600
    assert stale_path.is_dir()


def test_codex_repairs_same_version_runtime_content_drift(
    desired: DesiredState, tmp_path: Path
) -> None:
    stale_name = DOMAIN_BUNDLES[0]
    codex_home = tmp_path / "codex-home"
    installed = codex_home / f"plugins/cache/manifest/{stale_name}/0.2.0"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("stale cache\n", encoding="utf-8")
    row = json.loads(installed_json(desired, names=(stale_name,)))["installed"][0]
    row["installedPath"] = str(installed)
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=json.dumps({"installed": [row]})),
            command(stdout=plugin_remove_json(stale_name)),
            command(stdout=plugin_add_json(desired, stale_name)),
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES[1:]
            ],
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired)),
            command(stdout=mcp_list_json()),
        ]
    )
    adapter = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"CODEX_HOME": str(codex_home), "HOME": str(tmp_path / "home")},
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    )

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert [
        "codex",
        "plugin",
        "remove",
        f"{stale_name}@manifest",
        "--json",
    ] in runner.log


def test_codex_ambiguous_remove_failure_restores_verified_backup(
    desired: DesiredState, tmp_path: Path
) -> None:
    stale_name = DOMAIN_BUNDLES[0]
    stale_path = desired.bundle_path(stale_name)

    class RemovingRunner(QueueRunner):
        def run(self, argv, *, env=None):
            if list(argv[1:3]) == ["plugin", "remove"]:
                shutil.rmtree(stale_path)
            return super().run(argv, env=env)

    runner = RemovingRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired, "0.1.0", names=(stale_name,))),
            command(returncode=1, stderr="ambiguous native failure"),
            command(stdout=json.dumps({"installed": []})),
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES[1:]
            ],
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired)),
        ]
    )

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"HOME": str(tmp_path / "home")},
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(desired)

    assert result.state is ResultState.BLOCKED
    assert stale_path.is_dir()
    assert "verified prior plugin was restored" in " ".join(result.errors)


def test_codex_inspect_reports_selected_version_drift(desired: DesiredState) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired, "0.1.0")),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in result.errors[0]


def test_codex_inspect_reports_disabled_marketplace_addon_as_drift(
    desired: DesiredState,
) -> None:
    catalog = (
        *(CatalogPlugin(name, "0.2.0", f"./plugins/{name}") for name in DOMAIN_BUNDLES),
        CatalogPlugin("manifest-addon", "1.0.0", "./plugins/manifest-addon"),
    )
    rows = json.loads(installed_json(desired))["installed"]
    rows.append(
        {
            "pluginId": "manifest-addon@manifest",
            "version": "1.0.0",
            "installed": True,
            "enabled": False,
        }
    )
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=json.dumps({"installed": rows})),
            command(stdout=mcp_list_json()),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).inspect(
        replace(desired, catalog_plugins=catalog)
    )

    assert result.state is ResultState.DRIFTED
    assert result.errors == ("plugin manifest-addon@manifest is disabled",)


def test_codex_inspect_blocks_when_required_component_evidence_is_missing(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired)),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda _name: None).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "manifest-workspace:executable:git" in " ".join(result.errors)
