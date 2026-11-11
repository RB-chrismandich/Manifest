"""OMP consumer-visible inspection and full-receipt authority contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.contract_verification import combine_results
from manifest_agent.adapters.omp_inventory import cross_checked_plugin
from manifest_agent.adapters.registry import AdapterRegistry
from manifest_agent.models import (
    HarnessReceipt,
    HarnessResult,
    NativeInspection,
    ResultState,
)
from manifest_agent.ownership import (
    authenticate_omp_receipt,
    omp_receipt_ownership_errors,
)
from manifest_agent.service import HARNESS_ORDER
from manifest_agent.service_state import ServiceReport
from manifest_agent.state import _SUPPORTED_HARNESSES, read_receipt
from tests.python.manifest_agent._omp_native_fixture import (
    get_json,
    make_adapter,
    make_desired,
    make_service,
    put_json,
)


def test_registry_resolves_the_sixth_omp_adapter() -> None:
    assert AdapterRegistry.names() == (
        "claude",
        "codex",
        "cursor",
        "antigravity",
        "devin",
        "omp",
    )
    assert AdapterRegistry.create("omp").name == "omp"


def test_harness_order_and_supported_harnesses_are_six() -> None:
    assert HARNESS_ORDER == (
        "claude",
        "codex",
        "cursor",
        "antigravity",
        "devin",
        "omp",
    )
    assert "omp" in _SUPPORTED_HARNESSES
    assert len(_SUPPORTED_HARNESSES) == 6


@pytest.fixture
def installed(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    assert service.install().state is ResultState.READY
    return desired, adapter, runner, service


def test_cross_checked_plugin_agrees_across_all_three_native_sources(installed):
    desired, adapter, _runner, _service = installed
    root, _market, registry, runtime, cli = adapter._snapshot()
    plugin_id = f"{desired.contracts[0].name}@manifest"
    row, error = cross_checked_plugin(
        plugin_id=plugin_id,
        marketplace="manifest",
        cli_entries=cli[plugin_id],
        registry_rows=registry[plugin_id],
        runtime_row=runtime["plugins"][f"@manifest/{desired.contracts[0].name}"],
        native_root=root,
    )
    assert error is None
    assert row["version"] == desired.release_version
    assert row["enabled"] is True


def test_cross_checked_plugin_missing_inventory_is_pristine_absence(tmp_path):
    row, error = cross_checked_plugin(
        plugin_id="manifest-docs@manifest",
        marketplace="manifest",
        cli_entries=[],
        registry_rows=[],
        runtime_row=None,
        native_root=tmp_path / ".omp",
    )
    assert row is None
    assert error is None


def test_actual_adapter_missing_inventory_never_converges(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    result = adapter.inspect(desired)
    assert result.state is ResultState.DRIFTED
    assert result.native_inspection is not None
    assert len(result.native_inspection.packages) == 9
    assert all(
        package.status == "missing" for package in result.native_inspection.packages
    )
    assert result.native_inspection.inventory_errors
    assert not (tmp_path / "state/ownership.key").exists()


@pytest.mark.parametrize(
    "relative,document",
    [
        ("marketplaces.json", []),
        ("marketplaces.json", {"version": 1, "marketplaces": [None]}),
        ("plugins/installed_plugins.json", []),
        (
            "plugins/installed_plugins.json",
            {"version": 2, "plugins": {"manifest-docs@manifest": [None]}},
        ),
        ("plugins/omp-plugins.lock.json", []),
        ("plugins/omp-plugins.lock.json", {"plugins": {"manifest-docs": None}}),
    ],
)
def test_malformed_native_inventory_returns_typed_errors(installed, relative, document):
    desired, adapter, _runner, service = installed
    put_json(adapter._native_root() / relative, document)
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    native = result.to_dict()["harnesses"]["omp"]["native_inspection"]
    assert native["inventory_errors"]
    assert native["activation"] == "not-observed"
    assert adapter.inspect(desired).errors


def test_native_missing_registry_with_live_runtime_is_not_pristine(installed):
    desired, adapter, _runner, service = installed
    (adapter._native_root() / "plugins/installed_plugins.json").unlink()
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    assert result.harnesses["omp"].native_inspection.inventory_errors
    assert adapter.inspect(desired).state is not ResultState.READY


def test_cross_checked_plugin_rejects_disabled_runtime_lock(installed):
    desired, adapter, _runner, service = installed
    root = adapter._native_root()
    registry = get_json(root / "plugins/installed_plugins.json", {})
    registry["plugins"]["manifest-docs@manifest"][0]["enabled"] = False
    put_json(root / "plugins/installed_plugins.json", registry)
    lock = get_json(root / "plugins/omp-plugins.lock.json", {})
    lock["plugins"]["@manifest/manifest-docs"]["enabled"] = False
    put_json(root / "plugins/omp-plugins.lock.json", lock)
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    package = next(
        package
        for package in result.harnesses["omp"].native_inspection.packages
        if package.package_name == "manifest-docs"
    )
    assert package.enabled is False
    assert package.status == "disabled"
    assert adapter.inspect(desired).errors


def test_cross_checked_plugin_fails_closed_on_stale_runtime_lock_version(installed):
    desired, adapter, _runner, service = installed
    path = adapter._native_root() / "plugins/omp-plugins.lock.json"
    lock = get_json(path, {})
    lock["plugins"]["@manifest/manifest-docs"]["version"] = "0.0.1"
    put_json(path, lock)
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    assert any("stale" in error for error in result.harnesses["omp"].errors)
    assert adapter.inspect(desired).state is not ResultState.READY


def test_cross_checked_plugin_rejects_scope_conflict_ambiguity(installed):
    desired, adapter, _runner, service = installed
    path = adapter._native_root() / "plugins/installed_plugins.json"
    registry = get_json(path, {})
    registry["plugins"]["manifest-docs@manifest"].append(
        {"scope": "project", "version": "1.0.0", "installPath": "/other/path"}
    )
    put_json(path, registry)
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    assert any("scope" in error for error in result.harnesses["omp"].errors)
    assert adapter.inspect(desired).native_inspection.inventory_errors


def test_cross_checked_plugin_rejects_path_outside_exact_root(installed, tmp_path):
    desired, adapter, _runner, service = installed
    path = adapter._native_root() / "plugins/installed_plugins.json"
    registry = get_json(path, {})
    original = Path(registry["plugins"]["manifest-docs@manifest"][0]["installPath"])
    sibling = tmp_path / "foreign" / original.name
    sibling.mkdir(parents=True)
    registry["plugins"]["manifest-docs@manifest"][0]["installPath"] = str(sibling)
    put_json(path, registry)
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    assert any(
        "content-addressed" in error or "link" in error
        for error in result.harnesses["omp"].errors
    )
    assert adapter.inspect(desired).state is not ResultState.READY


def test_runtime_only_and_wrong_link_are_not_discovered(installed, tmp_path):
    _desired, adapter, _runner, service = installed
    root = adapter._native_root()
    link = root / "plugins/node_modules/@manifest/manifest-docs"
    link.unlink()
    link.symlink_to(tmp_path)
    result = service.reconcile()
    assert result.state is ResultState.BLOCKED
    assert result.harnesses["omp"].native_inspection.inventory_errors


def test_project_inventory_refuses_mutation_with_typed_diagnostics(installed, tmp_path):
    desired, adapter, runner, service = installed
    put_json(
        tmp_path / ".omp/plugins/installed_plugins.json", {"version": 2, "plugins": {}}
    )
    before = tuple(runner.mutations)
    result = service.reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert adapter.inspect(desired).native_inspection.inventory_errors


def test_package_lifecycle_is_not_runtime_or_mcp_qualification(installed):
    desired, adapter, runner, service = installed
    result = service.reconcile()
    assert result.state is ResultState.READY
    native = result.to_dict()["harnesses"]["omp"]["native_inspection"]
    assert native["activation"] == "not-observed"
    assert all(package["status"] == "verified" for package in native["packages"])
    assert any(
        component["kind"] == "mcp" and component["status"] == "unobserved"
        for component in native["components"]
    )
    assert any(
        component["kind"] == "agent" and component["status"] == "unsupported"
        for component in native["components"]
    )
    assert all(
        component["provenance"] == "native-resolver"
        for component in native["components"]
        if component["kind"] == "skill"
    )
    assert not any("mcp" in command for command in runner.calls)
    assert adapter.inspect(desired).state is ResultState.READY


def test_skill_resolver_sibling_prefix_never_counts_as_native_resolution(
    installed, tmp_path
):
    desired, adapter, runner, _service = installed
    sibling = (
        adapter._native_root()
        / "plugins/cache/plugins/manifest___manifest-docs___1.0.0"
        / "skills/manifest-docs-skill-extra/SKILL.md"
    )
    sibling.parent.mkdir()
    sibling.write_text("foreign\n")
    runner.skill_override = sibling
    native = adapter.inspect(desired).native_inspection
    assert all(
        component.status == "unresolved"
        for component in native.components
        if component.kind == "skill"
    )
    assert native.activation == "not-observed"


def test_combine_results_preserves_rightmost_native_inspection_not_merged_facts():
    first = NativeInspection("omp", "user", "/home/.omp", inventory_errors=("stale",))
    second = NativeInspection("omp", "user", "/home/.omp")
    combined = combine_results(
        HarnessResult("omp", ResultState.DRIFTED, (), {}, native_inspection=first),
        HarnessResult("omp", ResultState.READY, (), {}, native_inspection=second),
    )
    assert combined.native_inspection is second
    assert combined.native_inspection.inventory_errors == ()


def test_combine_results_keeps_native_inspection_when_later_result_has_none():
    native = NativeInspection("omp", "user", "/home/.omp")
    combined = combine_results(
        HarnessResult("omp", ResultState.READY, (), {}, native_inspection=native),
        HarnessResult("omp", ResultState.READY, (), {}),
    )
    assert combined.native_inspection is native
    document = ServiceReport("inspect", ResultState.READY, {"omp": combined}).to_dict()
    assert (
        document["harnesses"]["omp"]["native_inspection"]["activation"]
        == "not-observed"
    )


def test_omp_receipt_authentication_round_trips(installed):
    _desired, _adapter, _runner, service = installed
    signed = read_receipt(service.receipt_path).harnesses["omp"]
    assert (
        omp_receipt_ownership_errors(
            signed, key_path=service.receipt_path.parent / "ownership.key"
        )
        == ()
    )


def test_omp_receipt_authentication_detects_tamper(installed):
    _desired, adapter, runner, service = installed
    signed = read_receipt(service.receipt_path).harnesses["omp"]
    tampered = replace(signed, plugin_ids=())
    errors = omp_receipt_ownership_errors(
        tampered, key_path=service.receipt_path.parent / "ownership.key"
    )
    assert errors != ()
    before = tuple(runner.mutations)
    assert adapter.uninstall(tampered).state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before


def test_omp_receipt_authentication_rejects_wrong_key(installed, tmp_path):
    _desired, adapter, _runner, service = installed
    signed = read_receipt(service.receipt_path).harnesses["omp"]
    key = tmp_path / "other/ownership.key"
    other = authenticate_omp_receipt(replace(signed, owned_entries=()), key_path=key)
    assert omp_receipt_ownership_errors(signed, key_path=key) != ()
    assert adapter.uninstall(other).state is ResultState.BLOCKED


def test_omp_receipt_missing_auth_entry_is_explicit_not_silent():
    unsigned = HarnessReceipt("omp", "1", "18.6.1", (), (), {}, True)
    errors = omp_receipt_ownership_errors(unsigned, key_path=Path("/nonexistent"))
    assert errors != ()
    assert "predates OMP" in errors[0]


@pytest.mark.parametrize(
    "relative",
    [
        "marketplaces.json",
        "plugins/installed_plugins.json",
        "plugins/omp-plugins.lock.json",
    ],
)
def test_invalid_native_json_returns_typed_errors_without_mutation(installed, relative):
    _desired, adapter, runner, service = installed
    (adapter._native_root() / relative).write_text("{broken")
    before = tuple(runner.mutations)
    result = service.reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert result.harnesses["omp"].native_inspection.inventory_errors
    assert tuple(runner.mutations) == before


@pytest.mark.parametrize("location", ["project", "profile"])
def test_runtime_only_project_or_profile_layout_is_not_pristine(
    installed, tmp_path, location
):
    desired, adapter, runner, service = installed
    base = (
        tmp_path / ".omp"
        if location == "project"
        else adapter._native_root() / "profiles/secondary"
    )
    put_json(
        base / "plugins/omp-plugins.lock.json",
        {"plugins": {"foreign": {"version": "1"}}, "settings": {}},
    )
    before = tuple(runner.mutations)
    result = service.reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert result.harnesses["omp"].native_inspection.inventory_errors
    assert tuple(runner.mutations) == before
    assert adapter.inspect(desired).state is ResultState.BLOCKED
