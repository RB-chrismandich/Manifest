"""PR #1054 review regressions: checkout drift, recovery catalog, restore capture."""

import json
from pathlib import Path

from manifest_agent.adapters.omp_identity import MARKETPLACE_KIND, decode_identity
from manifest_agent.models import ResultState
from manifest_agent.ownership import omp_receipt_ownership_errors
from tests.python.manifest_agent._omp_native_fixture import (
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
