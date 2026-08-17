"""Codex native uninstall tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.adapters.codex as codex_module
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.adapters.codex_catalog import authenticated_marketplace
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import (
    owned_codex_catalog_entry,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    _catalog_entry,
    _receipt,
    command,
    marketplace_json,
    plugin_remove_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)


def test_codex_uninstall_retains_marketplace_for_unowned_plugin(tmp_path: Path) -> None:
    runner = QueueRunner([])
    receipt = _receipt(
        tmp_path,
        harness="codex",
        adapter_version="1",
        native_version="0.146",
        plugin_ids=tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES),
        owned_entries=(
            OwnedEntry("marketplace", "manifest", "receipt"),
            _catalog_entry(DOMAIN_BUNDLES, tmp_path),
        ),
        capabilities={},
        verified=True,
    )
    # One response is reused for each native remove before the final list.
    runner.results = [
        command(stdout=marketplace_json(str(tmp_path), tmp_path)),
        *[command(stdout=plugin_remove_json(name)) for name in DOMAIN_BUNDLES],
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
        ),
    ]

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path)},
    ).uninstall(receipt)

    assert result.state is ResultState.READY
    assert all(row[-1] == "--json" for row in runner.log[: len(DOMAIN_BUNDLES)])
    assert not any(
        row[1:4] == ["plugin", "marketplace", "remove"] for row in runner.log
    )
    assert "unowned plugin" in result.warnings[0]


def test_codex_uninstall_removes_owned_marketplace_when_unreferenced(
    tmp_path: Path,
) -> None:
    runner = QueueRunner(
        [command(stdout=marketplace_json(str(tmp_path), tmp_path))]
        + [command(stdout=plugin_remove_json(name)) for name in DOMAIN_BUNDLES]
        + [
            command(stdout=json.dumps({"installed": []})),
            command(
                stdout=json.dumps(
                    {"marketplaceName": "manifest", "installedRoot": None}
                )
            ),
            command(stdout=json.dumps({"marketplaces": []})),
        ]
    )
    receipt = _receipt(
        tmp_path,
        harness="codex",
        adapter_version="1",
        native_version="0.146",
        plugin_ids=DOMAIN_BUNDLES,
        owned_entries=(
            OwnedEntry("marketplace", "manifest", "receipt"),
            _catalog_entry(DOMAIN_BUNDLES, tmp_path),
        ),
        capabilities={},
        verified=True,
    )

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path)},
    ).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-2] == [
        "codex",
        "plugin",
        "marketplace",
        "remove",
        "manifest",
        "--json",
    ]
    assert runner.log[-1] == ["codex", "plugin", "marketplace", "list", "--json"]


def test_codex_uninstall_uses_exact_full_catalog_snapshot(tmp_path: Path) -> None:
    names = (*DOMAIN_BUNDLES, "manifest-i-have-adhd", "future-addon")
    runner = QueueRunner(
        [command(stdout=marketplace_json(str(tmp_path), tmp_path))]
        + [command(stdout=plugin_remove_json(name)) for name in names]
        + [command(stdout=json.dumps({"installed": []}))]
    )
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        tuple(f"{name}@manifest" for name in names),
        (_catalog_entry(names, tmp_path),),
        {},
        True,
    )

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path)},
    ).uninstall(receipt)

    assert result.state is ResultState.READY
    assert [row[3] for row in runner.log[1 : 1 + len(names)]] == [
        f"{name}@manifest" for name in names
    ]


@pytest.mark.parametrize("forgery", ("digest", "recomputed-snapshot", "extra-plugin"))
def test_codex_uninstall_rejects_forged_catalog_receipts_before_mutation(
    tmp_path: Path, forgery: str
) -> None:
    catalog = _catalog_entry(DOMAIN_BUNDLES, tmp_path)
    plugin_ids = tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES)
    runner = QueueRunner([])
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        plugin_ids,
        (OwnedEntry("marketplace", "manifest", "receipt"), catalog),
        {},
        True,
    )
    if forgery == "extra-plugin":
        receipt = replace(
            receipt, plugin_ids=(*receipt.plugin_ids, "future-addon@manifest")
        )
    else:
        entries = list(receipt.owned_entries)
        index = next(
            i for i, entry in enumerate(entries) if entry.kind == "codex-catalog"
        )
        forged_catalog = entries[index]
        if forgery == "digest":
            forged_catalog = replace(forged_catalog, identifier="0" * 64)
        else:
            document = json.loads(forged_catalog.previous_checksum or "")
            document["catalog"][0]["version"] = "9.9.9"
            canonical = json.dumps(
                document["catalog"], sort_keys=True, separators=(",", ":")
            ).encode()
            forged_catalog = replace(
                forged_catalog,
                identifier=hashlib.sha256(canonical).hexdigest(),
                previous_checksum=json.dumps(
                    document, sort_keys=True, separators=(",", ":")
                ),
            )
        entries[index] = forged_catalog
        receipt = replace(receipt, owned_entries=tuple(entries))

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path)},
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_codex_uninstall_resumes_prepared_plugin_removal(tmp_path: Path) -> None:
    names = ("manifest-workspace", "future-addon")
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        tuple(f"{name}@manifest" for name in names),
        (
            OwnedEntry("marketplace", "manifest", "receipt"),
            _catalog_entry(names, tmp_path),
        ),
        {},
        True,
    )
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    first_runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=plugin_remove_json(names[0])),
            command(returncode=1, stderr="native failure"),
        ]
    )
    first = CodexAdapter(
        runner=first_runner, which=lambda name: name, env=environment
    ).uninstall(receipt)
    assert first.state is ResultState.BLOCKED

    remaining = {
        "installed": [
            {
                "pluginId": f"{names[1]}@manifest",
                "version": "0.1.0",
                "installed": True,
            }
        ]
    }
    second_runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps(remaining)),
            command(stdout=plugin_remove_json(names[1])),
            command(stdout=json.dumps({"installed": []})),
            command(stdout='{"marketplaceName":"manifest","installedRoot":null}'),
            command(stdout='{"marketplaces":[]}'),
        ]
    )
    second = CodexAdapter(
        runner=second_runner, which=lambda name: name, env=environment
    ).uninstall(receipt)

    assert second.state is ResultState.READY
    assert second_runner.log[1] == ["codex", "plugin", "list", "--json"]
    assert second_runner.log[2][3] == f"{names[1]}@manifest"


def test_codex_uninstall_observes_completed_prepared_config_restoration(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = false\n',
        encoding="utf-8",
    )
    entry = OwnedEntry(
        "plugin-enabled-state",
        "i-have-adhd@i-have-adhd",
        "manifest",
        str(config),
        json.dumps(
            {"previous": True, "current": False, "written_sha256": "0" * 64},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    catalog = owned_codex_catalog_entry([], env=environment)
    receipt = _receipt(tmp_path, "codex", "1", "0.146", (), (entry, catalog), {}, True)
    saga_path = codex_module._uninstall_saga_path(receipt, environment)
    saga = codex_module._load_or_create_uninstall_saga(saga_path, receipt, ())
    step = "restore:0:plugin-enabled-state:i-have-adhd@i-have-adhd"
    codex_module._checkpoint_uninstall(saga_path, saga, step, "prepared")
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n',
        encoding="utf-8",
    )

    runner = QueueRunner(
        [
            command(stdout=marketplace_json("/manifest", "/manifest")),
            command(stdout=json.dumps({"installed": []})),
        ]
    )

    result = CodexAdapter(
        runner=runner, which=lambda name: name, env=environment
    ).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-1] == ["codex", "plugin", "list", "--json"]
    assert not saga_path.exists()


def test_codex_uninstall_blocks_ambiguous_prepared_config_restoration(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = false\n',
        encoding="utf-8",
    )
    entry = OwnedEntry(
        "plugin-enabled-state",
        "i-have-adhd@i-have-adhd",
        "manifest",
        str(config),
        json.dumps(
            {"previous": True, "current": False, "written_sha256": "0" * 64},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    catalog = owned_codex_catalog_entry([], env=environment)
    receipt = _receipt(tmp_path, "codex", "1", "0.146", (), (entry, catalog), {}, True)
    saga_path = codex_module._uninstall_saga_path(receipt, environment)
    saga = codex_module._load_or_create_uninstall_saga(saga_path, receipt, ())
    step = "restore:0:plugin-enabled-state:i-have-adhd@i-have-adhd"
    codex_module._checkpoint_uninstall(saga_path, saga, step, "prepared")
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nmode = "user"\n',
        encoding="utf-8",
    )

    result = CodexAdapter(
        runner=QueueRunner(
            [command(stdout=marketplace_json("/manifest", "/manifest"))]
        ),
        which=lambda name: name,
        env=environment,
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "ambiguous" in " ".join(result.errors)
    assert saga_path.exists()


def test_codex_uninstall_blocks_malformed_prepared_config_restoration(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text("not valid = [\n", encoding="utf-8")
    entry = OwnedEntry(
        "plugin-enabled-state",
        "i-have-adhd@i-have-adhd",
        "manifest",
        str(config),
        json.dumps(
            {"previous": True, "current": False, "written_sha256": "0" * 64},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    catalog = owned_codex_catalog_entry([], env=environment)
    receipt = _receipt(tmp_path, "codex", "1", "0.146", (), (entry, catalog), {}, True)

    result = CodexAdapter(
        runner=QueueRunner(
            [command(stdout=marketplace_json("/manifest", "/manifest"))]
        ),
        which=lambda name: name,
        env=environment,
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "ambiguous" in " ".join(result.errors)


def test_codex_uninstall_does_not_remove_marketplace_after_ambiguous_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        (),
        (
            OwnedEntry("marketplace", "manifest", "manifest"),
            _catalog_entry((), tmp_path),
        ),
        {},
        True,
    )
    expected = authenticated_marketplace(receipt, environment)
    assert expected is not None
    observations: list[AdapterMarketplaceState] = [expected]

    def observe(*, allow_absent: bool = False) -> AdapterMarketplaceState | None:
        del allow_absent
        if observations:
            return observations.pop()
        raise ValueError("Codex marketplace inventory is ambiguous")

    runner = QueueRunner([command(stdout=json.dumps({"installed": []}))])
    adapter = CodexAdapter(runner=runner, which=lambda name: name, env=environment)
    monkeypatch.setattr(adapter, "_observed_marketplace_identity", observe)

    result = adapter.uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "inventory is ambiguous" in " ".join(result.errors)
    assert runner.log == [["codex", "plugin", "list", "--json"]]


def test_codex_uninstall_accepts_prepared_marketplace_already_absent(
    tmp_path: Path,
) -> None:
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        (),
        (
            OwnedEntry("marketplace", "manifest", "manifest"),
            owned_codex_catalog_entry([], env=environment),
        ),
        {},
        True,
    )
    saga_path = codex_module._uninstall_saga_path(receipt, environment)
    saga = codex_module._load_or_create_uninstall_saga(saga_path, receipt, ())
    codex_module._checkpoint_uninstall(
        saga_path, saga, "remove:marketplace:manifest", "prepared"
    )
    runner = QueueRunner(
        [
            command(stdout='{"marketplaces":[]}'),
            command(stdout=json.dumps({"installed": []})),
        ]
    )

    result = CodexAdapter(
        runner=runner, which=lambda name: name, env=environment
    ).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log == [
        ["codex", "plugin", "marketplace", "list", "--json"],
        ["codex", "plugin", "list", "--json"],
    ]
