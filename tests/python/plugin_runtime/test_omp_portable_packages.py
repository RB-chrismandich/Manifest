"""Portable OMP package and marketplace inventory contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.python.plugin_runtime.omp_portable_support import put, run


def test_portable_package_agreement_is_never_activation(portable):
    native = run(portable, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["packages"][0]["status"] == "verified"
    assert native["packages"][0]["source_uri"] == "local"
    assert native["packages"][0]["source_provenance"] == "native-local-marketplace"
    assert native["activation"] == "not-observed"
    assert native["components"] == [
        {
            "kind": "skill",
            "identifier": "native-skill",
            "status": "resolved",
            "provenance": "omp-skill-list",
            "resolved_path": str(
                portable[1] / "plugins/cache/plugins/"
                "manifest___manifest-workspace___1.0.0/"
                "skills/native-skill/SKILL.md"
            ),
        }
    ]
    report = run(portable, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert report["verified"] is False
    assert any(
        row["reason"] == "native activation not verified"
        for row in report["unverified"]
    )


def test_github_marketplace_uses_matching_cached_catalog(portable):
    _scripts, root, _env, _cwd = portable
    source = "ManifestOrg/marketplace"
    marketplace = root / "marketplaces.json"
    registry = json.loads(marketplace.read_text())
    registry["marketplaces"][0].update(sourceType="github", sourceUri=source)
    put(marketplace, registry)
    cache = root / "plugins/cache/marketplaces/manifest/.claude-plugin/marketplace.json"
    catalog_path = root / "plugins/cache/marketplaces/manifest/marketplace.json"
    catalog = json.loads(catalog_path.read_text())
    put(cache, catalog)

    native = run(portable, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["inventory_errors"] == []
    assert native["packages"][0]["status"] == "verified"
    assert native["packages"][0]["source_uri"] == source
    assert native["packages"][0]["source_provenance"] == "native-github-marketplace"


@pytest.fixture
def mixed_marketplaces(portable):
    _scripts, root, env, _cwd = portable
    # External metadata attributes its runtime name only. No external link or
    # version/enabled validation belongs in Manifest's owned package report.
    cache = root / "plugins/cache/plugins/external___aaa-external___2.0.0"
    put(cache / "package.json", {"name": "@external/package", "version": "2.0.0"})
    entry = {"scope": "user", "version": "2.0.0", "installPath": str(cache)}
    registry_path = root / "plugins/installed_plugins.json"
    registry = json.loads(registry_path.read_text())
    registry["plugins"]["aaa-external@external"] = [entry]
    put(registry_path, registry)
    cli_path = Path(env["OMP_TEST_LIST"])
    cli = json.loads(cli_path.read_text())
    cli["marketplace"].insert(
        0,
        {
            "id": "aaa-external@external",
            "scope": "user",
            "entries": [entry],
        },
    )
    put(cli_path, cli)
    lock_path = root / "plugins/omp-plugins.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["plugins"]["@external/package"] = {"version": "old", "enabled": False}
    put(lock_path, lock)
    return portable


def test_mixed_marketplaces_report_only_manifest_packages(mixed_marketplaces):
    native = run(mixed_marketplaces, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["inventory_errors"] == []
    assert [row["package_id"] for row in native["packages"]] == [
        "manifest-workspace@manifest",
    ]
    assert native["packages"][0]["status"] == "verified"
    assert [row["identifier"] for row in native["components"]] == ["native-skill"]
    report = run(mixed_marketplaces, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert report["verified"] is False
    assert any(
        row["reason"] == "native activation not verified"
        for row in report["unverified"]
    )
    assert "external" not in json.dumps(report)


@pytest.mark.parametrize("mismatch", ["cli-only", "registry-only", "entries"])
def test_mixed_marketplaces_preserve_full_native_parity(mixed_marketplaces, mismatch):
    _scripts, root, env, _cwd = mixed_marketplaces
    registry_path = root / "plugins/installed_plugins.json"
    registry = json.loads(registry_path.read_text())
    cli_path = Path(env["OMP_TEST_LIST"])
    cli = json.loads(cli_path.read_text())
    if mismatch == "cli-only":
        del registry["plugins"]["aaa-external@external"]
    elif mismatch == "registry-only":
        cli["marketplace"] = cli["marketplace"][1:]
    else:
        cli["marketplace"][0]["entries"][0]["version"] = "different"
    put(registry_path, registry)
    put(cli_path, cli)
    native = run(mixed_marketplaces, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["packages"] == []
    assert native["inventory_errors"] == [
        "OMP CLI and installed registry package "
        + ("entries" if mismatch == "entries" else "sets")
        + " disagree",
    ]


@pytest.mark.parametrize(
    "runtime_name",
    [
        "@manifest/orphan",
        "manifest-orphan",
        "unattributed-orphan",
    ],
)
def test_mixed_marketplaces_preserve_manifest_runtime_orphans(
    mixed_marketplaces,
    runtime_name,
):
    _scripts, root, _env, _cwd = mixed_marketplaces
    path = root / "plugins/omp-plugins.lock.json"
    lock = json.loads(path.read_text())
    lock["plugins"][runtime_name] = {"version": "1.0.0", "enabled": True}
    put(path, lock)
    native = run(mixed_marketplaces, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["packages"][0]["status"] == "verified"
    assert native["inventory_errors"] == [
        "OMP runtime-only stale inventory is unsupported"
    ]


@pytest.mark.parametrize("failure", ["disabled", "stale", "identity", "enabled"])
def test_mixed_marketplaces_preserve_manifest_validation(mixed_marketplaces, failure):
    _scripts, root, _env, _cwd = mixed_marketplaces
    lock_path = root / "plugins/omp-plugins.lock.json"
    lock = json.loads(lock_path.read_text())
    if failure == "identity":
        cache = root / "plugins/cache/plugins/manifest___manifest-workspace___1.0.0"
        put(cache / "package.json", {"name": [], "version": "1.0.0"})
    else:
        lock["plugins"]["@manifest/workspace"].update(
            {
                "version": "old" if failure == "stale" else "1.0.0",
                "enabled": "yes" if failure == "enabled" else failure != "disabled",
            }
        )
        put(lock_path, lock)
    native = run(mixed_marketplaces, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert len(native["packages"]) == 1
    assert native["packages"][0]["status"] == (
        "disabled" if failure == "disabled" else "inconsistent"
    )
    assert native["inventory_errors"]
    report = run(mixed_marketplaces, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert report["verified"] is False
    assert "external" not in json.dumps(report)


@pytest.mark.parametrize(
    "plugin_id",
    [
        "manifest-workspace@manifest@external",
        "manifest/workspace@external",
        "manifest workspace@external",
        "@external",
        "manifest-workspace@",
    ],
)
def test_malformed_marketplace_ids_cannot_escape_manifest_scope(
    mixed_marketplaces,
    plugin_id,
):
    _scripts, root, env, _cwd = mixed_marketplaces
    registry_path = root / "plugins/installed_plugins.json"
    registry = json.loads(registry_path.read_text())
    registry["plugins"][plugin_id] = registry["plugins"].pop(
        "manifest-workspace@manifest"
    )
    put(registry_path, registry)
    cli_path = Path(env["OMP_TEST_LIST"])
    cli = json.loads(cli_path.read_text())
    cli["marketplace"][1]["id"] = plugin_id
    put(cli_path, cli)
    native = run(mixed_marketplaces, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["packages"] == []
    assert native["inventory_errors"] == [
        "OMP marketplace package identity is malformed"
    ]
    report = run(mixed_marketplaces, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert report["verified"] is False
    assert any(
        "native inventory unreadable" in row["reason"] for row in report["unverified"]
    )


@pytest.mark.parametrize("failure", ["missing-cache", "stale-cache"])
def test_github_marketplace_requires_current_cached_catalog(portable, failure):
    _scripts, root, _env, _cwd = portable
    registry_path = root / "marketplaces.json"
    registry = json.loads(registry_path.read_text())
    registry["marketplaces"][0].update(
        sourceType="github",
        sourceUri="ManifestOrg/marketplace",
    )
    put(registry_path, registry)
    cache = root / "plugins/cache/marketplaces/manifest/.claude-plugin/marketplace.json"
    if failure == "missing-cache":
        cache.parent.mkdir(parents=True, exist_ok=True)
    else:
        put(cache, {"name": "manifest", "plugins": []})

    document = run(portable, "omp_native_inspection.py")
    native = document["harnesses"]["omp"]["native_inspection"]
    assert native["packages"] == []
    assert native["inventory_errors"] == ["OMP marketplace catalog is missing or stale"]
    assert "ManifestOrg/marketplace" not in json.dumps(document)


@pytest.mark.parametrize(
    ("source_type", "source_uri"),
    [
        ("github", "https://github.com/ManifestOrg/marketplace"),
        ("github", "ManifestOrg/marketplace?token=secret"),
        ("unsupported", "private-secret-value"),
    ],
)
def test_unsupported_marketplace_sources_fail_closed_without_uri_leak(
    portable,
    source_type,
    source_uri,
):
    _scripts, root, _env, _cwd = portable
    registry_path = root / "marketplaces.json"
    registry = json.loads(registry_path.read_text())
    registry["marketplaces"][0].update(sourceType=source_type, sourceUri=source_uri)
    put(registry_path, registry)

    document = run(portable, "omp_native_inspection.py")
    native = document["harnesses"]["omp"]["native_inspection"]
    assert native["packages"] == []
    assert native["inventory_errors"] == [
        "OMP marketplace source is unsupported or mismatched",
    ]
    assert source_uri not in json.dumps(document)
