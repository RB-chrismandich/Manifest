"""Receipts that still name a retired harness (Gemini CLI) keep working."""

import json
from pathlib import Path

import pytest

from manifest_agent.models import ResultState
from manifest_agent.retired_harnesses import (
    RETIRED_HARNESSES,
    retired_harness_notes,
    retired_receipt_harnesses,
)
from manifest_agent.state import StateError, read_receipt, write_receipt_atomic
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    bump_release,
    legacy_skill_home,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)
from tests.python.manifest_agent.test_state import SAMPLE_RECEIPT

# The shape observed on real machines after the Gemini CLI was uninstalled: an
# unverified record whose only evidence is a blocked Context7 MCP entry.
_GEMINI_RECORD = {
    "harness": "gemini",
    "adapter_version": "1",
    "native_version": "unknown",
    "plugin_ids": [],
    "owned_entries": [],
    "capabilities": {"mcp:context7": "blocked"},
    "verified": False,
    "errors": ["native command exited 1; stderr: consent banner"],
}


def _add_record(path: Path, name: str, record: dict) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    document["harnesses"][name] = record
    path.write_text(json.dumps(document), encoding="utf-8")


def _raw_harnesses(path: Path) -> set[str]:
    return set(json.loads(path.read_text(encoding="utf-8"))["harnesses"])


def test_gemini_is_the_retired_harness() -> None:
    assert frozenset({"gemini"}) == RETIRED_HARNESSES


def test_receipt_with_retired_gemini_record_loads_without_it(tmp_path: Path) -> None:
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    _add_record(path, "gemini", _GEMINI_RECORD)

    receipt = read_receipt(path)

    assert receipt == SAMPLE_RECEIPT
    assert retired_receipt_harnesses(path) == ("gemini",)


def test_unknown_harness_is_still_rejected_beside_a_retired_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    _add_record(path, "gemini", _GEMINI_RECORD)
    _add_record(path, "future-harness", {**_GEMINI_RECORD, "harness": "future-harness"})

    with pytest.raises(StateError, match="unsupported receipt harness: future-harness"):
        read_receipt(path)


def test_retired_record_is_never_written_back(tmp_path: Path) -> None:
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    _add_record(path, "gemini", _GEMINI_RECORD)

    receipt = read_receipt(path)
    assert receipt is not None
    write_receipt_atomic(path, receipt)

    assert _raw_harnesses(path) == {"claude"}


def test_retired_probe_tolerates_missing_and_malformed_receipts(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")

    assert retired_receipt_harnesses(missing) == ()
    assert retired_receipt_harnesses(malformed) == ()


def test_notes_distinguish_pruned_from_pending() -> None:
    assert retired_harness_notes(("gemini",), ()) == (
        "gemini: retired harness record pruned from the receipt "
        "(Gemini CLI support was removed)",
    )
    assert retired_harness_notes(("gemini",), ("gemini",)) == (
        "gemini: retired harness record ignored; it is pruned on the next "
        "receipt write (Gemini CLI support was removed)",
    )


@pytest.fixture
def installed(tmp_path: Path):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = make_service_factory(tmp_path)({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    _add_record(service.receipt_path, "gemini", _GEMINI_RECORD)
    return service, claude, codex


def test_bootstrap_sync_release_change_proceeds_and_prunes_retired_record(
    installed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A release change used to demand every receipt-owned harness, so a dead
    gemini record blocked with 'unavailable: gemini'."""
    service, claude, codex = installed
    bump_release(service)
    service.harnesses = ("codex",)
    claude.calls.clear()
    codex.calls.clear()
    legacy_skill_home(tmp_path, monkeypatch)

    result = service.bootstrap_sync()

    assert result.state is ResultState.READY, result.errors
    assert not any("gemini" in error for error in result.errors)
    assert "install" in codex.calls
    assert _raw_harnesses(service.receipt_path) == {"claude", "codex"}
    assert (
        "gemini: retired harness record pruned from the receipt "
        "(Gemini CLI support was removed)"
    ) in result.notes
    assert result.to_dict()["notes"] == list(result.notes)


def test_update_reconcile_proceeds_for_remaining_harnesses(installed) -> None:
    service, _claude, _codex = installed

    result = service.reconcile(apply=True)

    assert result.state is not ResultState.BLOCKED, result.errors
    assert set(result.harnesses) <= {"claude", "codex"}
    assert any(
        note.startswith("gemini: retired harness record") for note in result.notes
    )


def test_read_only_reconcile_notes_the_pending_prune(installed) -> None:
    service, _claude, _codex = installed

    result = service.reconcile(apply=False)

    assert "gemini" not in result.harnesses
    assert _raw_harnesses(service.receipt_path) == {"claude", "codex", "gemini"}
    assert (
        "gemini: retired harness record ignored; it is pruned on the next receipt "
        "write (Gemini CLI support was removed)"
    ) in result.notes


def test_install_rewrites_the_receipt_without_the_retired_record(installed) -> None:
    service, _claude, _codex = installed

    result = service.install()

    assert result.state is ResultState.READY, result.errors
    assert _raw_harnesses(service.receipt_path) == {"claude", "codex"}
    assert any("pruned from the receipt" in note for note in result.notes)


def test_receipt_without_retired_records_gets_no_note(tmp_path: Path) -> None:
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = make_service_factory(tmp_path)({"claude": claude, "codex": codex})

    result = service.install()

    assert not any("retired harness" in note for note in result.notes)
