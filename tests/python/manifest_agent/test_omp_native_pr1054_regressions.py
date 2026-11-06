"""PR #1054 review regressions: checkout drift, recovery catalog, restore capture."""

import json
from pathlib import Path

from manifest_agent.adapters.omp_identity import MARKETPLACE_KIND, decode_identity
from manifest_agent.models import ResultState
from manifest_agent.ownership import omp_receipt_ownership_errors
from tests.python.manifest_agent._omp_native_fixture import (
    make_adapter,
    make_desired,
    make_service,
)
from tests.python.manifest_agent.test_omp_native_lifecycle import (
    owned,
    setup_install,
)


def _marketplace_source(service):
    entry = next(
        entry
        for entry in owned(service).owned_entries
        if entry.kind == MARKETPLACE_KIND
    )
    return decode_identity(entry)["source"]


def test_checkout_edit_does_not_block_uninstall_ownership(tmp_path: Path):
    desired, _adapter, _runner, service = setup_install(tmp_path)
    skill = desired.release_root / "plugins/manifest-i-have-adhd/skills"
    skill_file = next(skill.glob("*/SKILL.md"))
    skill_file.write_text(skill_file.read_text() + "\nlocal edit\n")

    assert (
        omp_receipt_ownership_errors(
            owned(service), key_path=service.receipt_path.parent / "ownership.key"
        )
        == ()
    )
    assert service.uninstall().state is ResultState.READY


def test_edited_recovery_catalog_is_rejected_before_registry_change(tmp_path: Path):
    desired, adapter, runner, _service = setup_install(tmp_path)
    catalog = desired.release_root / ".claude-plugin/marketplace.json"
    catalog_obj = json.loads(catalog.read_text())
    catalog_obj["description"] = "locally edited"
    catalog.write_text(json.dumps(catalog_obj))
    mutations_before = len(runner.mutations)

    replacement = make_desired(tmp_path / "release2", version="1.0.1")
    next_service = make_service(tmp_path, adapter, replacement)
    report = next_service.reconcile(apply=True)

    assert report.state is not ResultState.READY
    assert not any(
        "remove" in command for command in runner.mutations[mutations_before:]
    )


def test_shadow_inspect_ignores_real_home_project_inventory(tmp_path: Path):
    real_home = tmp_path / "home"
    checkout = real_home / "project"
    (real_home / ".omp" / "plugins").mkdir(parents=True)
    checkout.mkdir(parents=True)
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    adapter._env = {**adapter._env, "HOME": str(real_home)}
    adapter._cwd = checkout.resolve(strict=True)

    report = adapter.shadow_inspect(desired, tmp_path / "shadow-home")
    assert not any("project inventory" in error for error in report.errors)


def test_deleted_checkout_does_not_block_uninstall_ownership(tmp_path: Path):
    import shutil

    desired, _adapter, _runner, service = setup_install(tmp_path)
    shutil.rmtree(desired.release_root)

    assert (
        omp_receipt_ownership_errors(
            owned(service), key_path=service.receipt_path.parent / "ownership.key"
        )
        == ()
    )
    assert service.uninstall().state is ResultState.READY


def test_shadow_home_nested_under_real_home_ignores_real_project_inventory(
    tmp_path: Path,
):
    real_home = tmp_path / "home"
    (real_home / ".omp" / "plugins").mkdir(parents=True)
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    adapter._env = {**adapter._env, "HOME": str(real_home)}
    adapter._cwd = (real_home / "project").resolve(strict=False)
    (real_home / "project").mkdir()

    report = adapter.shadow_inspect(desired, real_home / "shadow")
    assert not any("project inventory" in error for error in report.errors)


def test_same_version_source_edit_is_not_reported_ready(tmp_path):
    desired, _adapter, _runner, service = setup_install(tmp_path)
    skill = next(desired.bundle_path("manifest-i-have-adhd").glob("skills/*/SKILL.md"))
    skill.write_text(skill.read_text() + "\nEdited in place.\n")
    result = service.reconcile(apply=True)
    assert result.state is not ResultState.READY



def test_post_install_capture_failure_keeps_original_command_error(tmp_path):
    """A snapshot failure in the install finally must not mask the command error."""
    from manifest_agent.adapters.omp_inventory import OmpInventoryError

    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    make_service(tmp_path, adapter, desired)
    original_command = adapter._command
    original_snapshot = adapter._snapshot
    state = {"failed_once": False, "fail_next_snapshot": False}

    def failing_command(argv, **kwargs):
        if argv[1] == "plugin" and not state["failed_once"]:
            state["failed_once"] = True
            state["fail_next_snapshot"] = True
            raise OmpInventoryError("OMP native command failed: exit 1: boom")
        return original_command(argv, **kwargs)

    def flaky_snapshot():
        if state["fail_next_snapshot"]:
            state["fail_next_snapshot"] = False
            raise OSError("snapshot unreadable after mutation")
        return original_snapshot()

    adapter._command = failing_command
    adapter._snapshot = flaky_snapshot

    result = adapter.install(desired)

    assert state["failed_once"]
    assert result.state is ResultState.BLOCKED
    assert any("boom" in error for error in result.errors), result.errors


def test_marketplace_identity_failure_keeps_original_command_error(tmp_path, monkeypatch):
    """Identity validation in the marketplace finally must not mask the command error."""
    from manifest_agent.adapters import omp_lifecycle
    from manifest_agent.adapters.omp_inventory import OmpInventoryError

    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    make_service(tmp_path, adapter, desired)
    original_command = adapter._command
    state = {"failed_once": False}

    def failing_marketplace_add(argv, **kwargs):
        if argv[1:3] == ("plugin", "marketplace") and not state["failed_once"]:
            state["failed_once"] = True
            original_command(argv, **kwargs)
            raise OmpInventoryError("OMP native command failed: exit 1: boom")
        return original_command(argv, **kwargs)

    def rejecting_identity(*_args, **_kwargs):
        raise ValueError("marketplace source unexpected")

    adapter._command = failing_marketplace_add
    monkeypatch.setattr(omp_lifecycle, "marketplace_identity", rejecting_identity)

    result = adapter.install(desired)

    assert state["failed_once"]
    assert result.state is ResultState.BLOCKED
    assert any("boom" in error for error in result.errors), result.errors
    assert any("post-install capture failed" in error for error in result.errors), result.errors


def test_foreign_marketplace_source_blocks_plugin_install(tmp_path, monkeypatch):
    """A created marketplace with an unexpected source must not receive plugin installs."""
    from manifest_agent.adapters import omp_lifecycle

    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    make_service(tmp_path, adapter, desired)
    original_command = adapter._command
    plugin_mutations = []

    def recording_command(argv, **kwargs):
        if argv[1] == "plugin" and argv[2] in ("install", "upgrade"):
            plugin_mutations.append(tuple(argv))
        return original_command(argv, **kwargs)

    def foreign_identity(*_args, **_kwargs):
        return {"source": "/elsewhere"}

    adapter._command = recording_command
    monkeypatch.setattr(omp_lifecycle, "marketplace_identity", foreign_identity)

    result = adapter.install(desired)

    assert result.state is ResultState.BLOCKED
    assert any("unexpected source" in error for error in result.errors), result.errors
    assert plugin_mutations == [], plugin_mutations
