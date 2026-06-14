"""T038 — US5: secret/PII redaction in the durable audit (FR-038, SC-016)."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import redact, audit  # noqa: E402

# Corpus of secrets/PII that must NEVER appear unredacted in the audit (SC-016).
SECRETS = [
    "sk-ant-abcdef0123456789",
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "glpat-ABCDEFGHIJ1234567890",
    "AKIAIOSFODNN7EXAMPLE",
    "Authorization: Bearer supersecrettoken123456",
    "api_key=deadbeefcafebabe1234",
    "alice.engineer@example.com",
]


def test_redact_text_masks_each_secret():
    for s in SECRETS:
        assert "REDACTED" in redact.redact_text(s), f"not redacted: {s}"


def test_scrub_recurses_structures():
    record = {"reasoning_log": ["used ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 to auth"],
              "nested": {"email": "bob@example.com", "list": ["sk-ant-zzzzzzzzzzzz"]}}
    scrubbed = redact.scrub(record)
    blob = json.dumps(scrubbed)
    assert "ghp_ABCDEF" not in blob
    assert "bob@example.com" not in blob
    assert "sk-ant-zzz" not in blob


def test_audit_persists_only_redacted_content(tmp_path):
    log = audit.AuditLog(tmp_path, run_id="r1")
    envelope = {"phase": 1, "status": "ok",
                "reasoning_log": [f"secret {s}" for s in SECRETS], "escalation": None}
    assert log.record_response(envelope) is True
    written = log.path.read_text()
    for s in SECRETS:
        assert s not in written, f"leaked into audit: {s}"   # SC-016
    # the audit line is still valid JSON
    for line in written.strip().splitlines():
        json.loads(line)


def test_base64_and_short_secrets_redacted():  # bug_012
    assert "REDACTED" in redact.redact_text("token=abc+def/ghij==")      # base64 punctuation
    assert "abc+def/ghij" not in redact.redact_text("token=abc+def/ghij==")
    assert "REDACTED" in redact.redact_text("password=short1")           # < 8 chars, no floor
    out = redact.redact_text("api_key: longvaluestring123")
    assert ":" in out and "REDACTED" in out                              # separator preserved


def test_fallback_still_redacts_canonical_keys(monkeypatch):  # bug_003
    # Simulate skillclaw_scrub unavailable (identity base): _EXTRA must still cover canon keys.
    monkeypatch.setattr(redact, "_base_redact", lambda t: t)
    for s in ("sk-ant-abcdef0123456789", "sk-proj-deadbeef12345678abcd",
              "Authorization: Bearer supersecrettoken123456"):
        assert "REDACTED" in redact.redact_text(s), f"fallback leaked: {s}"


def test_audit_record_includes_payload(tmp_path):  # bug_019 / SC-010
    import json as _json
    log = audit.AuditLog(tmp_path, run_id="rp")
    env = {"phase": 1, "status": "ok",
           "payload": {"ranked_issue_ids": ["#11"], "top_choice_justification": "x", "dependency_notes": []},
           "reasoning_log": ["chose #11"], "escalation": None}
    log.record_response(env)
    rec = _json.loads(log.path.read_text().strip())
    assert rec["payload"]["ranked_issue_ids"] == ["#11"]   # decision content recoverable


def test_audit_dir_is_chmod_700(tmp_path):
    import os
    log = audit.AuditLog(tmp_path / "state", run_id="r2")
    log.append({"x": 1})
    mode = os.stat(log.dir).st_mode & 0o777
    assert mode == 0o700


def test_audit_fail_open_on_write_error(tmp_path, monkeypatch):
    log = audit.AuditLog(tmp_path, run_id="r3")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", boom)
    assert log.append({"x": 1}) is False   # fail-open: returns False, does not raise
