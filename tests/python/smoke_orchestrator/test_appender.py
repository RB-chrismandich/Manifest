"""US1 — SmokeTestAppender: idempotency, validation, concurrency (T011)."""

import sys
import threading
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator.appender import SmokeTestAppender
from smoke_orchestrator.validation import ValidationError


def _wf(test_id="login-flow", tier="Lite", title="Login"):
    return {
        "app": "demo",
        "id": test_id,
        "title": title,
        "tier": tier,
        "steps": [
            {"name": "open", "type": "api", "method": "GET", "path": "/health"},
        ],
    }


def _read(catalog_dir, app="demo"):
    return yaml.safe_load((Path(catalog_dir) / f"{app}.yaml").read_text())


def test_append_new_creates_valid_entry(tmp_path):
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    res = app.append(_wf())
    assert res.updated is False
    catalog = _read(tmp_path)
    assert catalog["version"] == 1 and catalog["app"] == "demo"
    assert [t["id"] for t in catalog["tests"]] == ["login-flow"]


def test_append_output_is_yamllint_indent_sequences_compliant(tmp_path):
    """The serialized catalog must indent sequence items under their parent key.

    yamllint's default `indentation: {indent-sequences: true}` (the repo config)
    rejects PyYAML's default indentless sequences, so `append` output would fail
    CI lint. Encode the rule structurally (no dependency on yamllint importable).
    """
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    app.append(_wf())
    text = (Path(tmp_path) / "demo.yaml").read_text()
    # sequence items indented under their key ...
    assert "\ntests:\n  - " in text, text
    assert "\n    steps:\n      - " in text, text
    # ... and never flush-left under a mapping key
    assert "\n- id:" not in text, text
    assert "\n  - name:" not in text, text
    # still parses back to the same data
    assert yaml.safe_load(text)["tests"][0]["id"] == "login-flow"


def test_append_is_idempotent_by_id(tmp_path):
    """SC-002: resubmitting the same id 10x yields exactly one entry."""
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    for i in range(10):
        res = app.append(_wf(title=f"Login v{i}"))
        assert res.updated == (i > 0)
    catalog = _read(tmp_path)
    assert len(catalog["tests"]) == 1
    assert catalog["tests"][0]["title"] == "Login v9"  # updated in place


def test_distinct_ids_coexist(tmp_path):
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    app.append(_wf(test_id="a"))
    app.append(_wf(test_id="b"))
    assert sorted(t["id"] for t in _read(tmp_path)["tests"]) == ["a", "b"]


def test_invalid_workflow_rejected_without_mutation(tmp_path):
    """FR-003: invalid input leaves the catalog untouched."""
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    app.append(_wf(test_id="good"))
    before = (tmp_path / "demo.yaml").read_text()

    bad = _wf(test_id="bad")
    del bad["tier"]  # missing required field
    with pytest.raises(ValidationError):
        app.append(bad)
    assert (tmp_path / "demo.yaml").read_text() == before  # unchanged


def test_unknown_tier_rejected(tmp_path):
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    bad = _wf()
    bad["tier"] = "Mega"
    with pytest.raises(ValidationError):
        app.append(bad)


def test_cli_command_must_be_list(tmp_path):
    """Security: a cli step's command must be an arg-array, never a shell string."""
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    bad = _wf()
    bad["steps"] = [{"name": "x", "type": "cli", "command": "rm -rf /"}]
    with pytest.raises(ValidationError):
        app.append(bad)


def test_dry_run_writes_nothing(tmp_path):
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    app.append(_wf(), dry_run=True)
    assert not (tmp_path / "demo.yaml").exists()


def test_concurrent_appends_do_not_corrupt(tmp_path):
    """FR-015: parallel appends of distinct ids all land, catalog stays valid."""
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    ids = [f"t{i}" for i in range(20)]

    def worker(tid):
        app.append(_wf(test_id=tid))

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    catalog = _read(tmp_path)
    assert sorted(t["id"] for t in catalog["tests"]) == sorted(ids)


def test_prune_is_idempotent(tmp_path):
    """FR-018: prune removes the test; pruning an absent id is a no-op."""
    app = SmokeTestAppender(catalog_dir=str(tmp_path))
    app.append(_wf(test_id="keep"))
    app.append(_wf(test_id="drop"))
    assert app.prune("demo", "drop") is True
    assert [t["id"] for t in _read(tmp_path)["tests"]] == ["keep"]
    assert app.prune("demo", "drop") is False  # already gone, no error
