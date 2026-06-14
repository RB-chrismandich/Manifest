"""T022 — US2: Phase 3/4/5 payloads conform to their schemas."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import engine, gates  # noqa: E402


def required(schema):
    return set(schema.get("required", []))


def test_phase4_payload_matches_schema_exactly():
    schema = engine.load_schema("phase4-analysis-gate")
    payload = gates.evaluate_analysis_gate([{"finding": "lint error", "severity": "error",
                                             "fix_directive": "fix it"}])
    # additionalProperties:false → payload keys must equal the schema's required set
    assert set(payload.keys()) == required(schema)
    assert payload["gate"] == "blocked" and payload["implement_approved"] is False


def test_phase5_payload_matches_schema_exactly():
    schema = engine.load_schema("phase5-verification-gate")
    payload = gates.evaluate_verification_gate([{"dimension": "standards", "tier": 2,
                                                 "detail": "naming", "remediation": None}])
    assert set(payload.keys()) == required(schema)
    assert set(payload["dimensions"].keys()) == {"design_intent", "functionality", "standards"}


def test_analysis_severity_coerced_to_enum():  # C5
    schema = engine.load_schema("phase4-analysis-gate")
    allowed = schema["properties"]["required_fixes"]["items"]["properties"]["severity"]["enum"]
    p = gates.evaluate_analysis_gate([{"finding": "x", "severity": "catastrophic", "fix_directive": "y"}])
    assert p["required_fixes"][0]["severity"] in allowed   # unknown coerced, schema-valid


def test_verification_unknown_tier_is_fail_closed():  # C6 / FR-033
    p = gates.evaluate_verification_gate([{"dimension": "standards", "detail": "no tier given"}])
    assert p["verdict"] == "blocked" and p["pr_open_approved"] is False
    assert p["findings"][0]["tier"] == 1                   # unclassified → Tier 1 blocker


def test_verification_unknown_dimension_coerced_to_enum():  # C6
    schema = engine.load_schema("phase5-verification-gate")
    allowed = schema["properties"]["findings"]["items"]["properties"]["dimension"]["enum"]
    p = gates.evaluate_verification_gate([{"dimension": "weird", "tier": 2, "detail": "x"}])
    assert p["findings"][0]["dimension"] in allowed


def test_phase3_sample_payload_conforms():
    schema = engine.load_schema("phase3-tasking")
    sample = {"tasks": [{
        "seq": 1, "title": "t", "description": "d",
        "acceptance_criteria": ["passes"], "speck_review_criteria_addressed": ["security"],
        "depends_on": [],
    }]}
    assert required(schema) <= sample.keys()
    task_required = set(schema["properties"]["tasks"]["items"]["required"])
    assert task_required <= sample["tasks"][0].keys()
