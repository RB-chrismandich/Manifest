"""T016 — US1: Phase 1 payload conforms to phase1-prioritization.schema.json."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import engine  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "orchestrator" / "backlog.json"


def _required_keys(schema):
    return set(schema.get("required", []))


def test_phase1_payload_has_required_keys_and_shape():
    schema = engine.load_schema("phase1-prioritization")
    issues = json.loads(FIXTURE.read_text())["issues"]
    payload = engine.prioritize(issues).to_payload()

    assert _required_keys(schema) <= payload.keys()
    assert isinstance(payload["ranked_issue_ids"], list)
    assert isinstance(payload["top_choice_justification"], str)
    for note in payload["dependency_notes"]:
        assert set(note.keys()) == {"issue_id", "blocks"}
        assert isinstance(note["blocks"], list)


def test_runtime_schema_matches_design_contract():
    """The copied runtime schema must be byte-identical to the spec contract (T004)."""
    runtime = (REPO_ROOT / "configs/claude/scripts/orchestrator/schemas/"
               "phase1-prioritization.schema.json").read_text()
    design = (REPO_ROOT / "specs/004-autonomous-issue-orchestrator/contracts/"
              "phase1-prioritization.schema.json").read_text()
    assert runtime == design
