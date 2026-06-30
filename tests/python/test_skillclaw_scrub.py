import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_scrub as scrub


def test_redacts_anthropic_and_openai_keys():
    text = "key sk-ant-api03-ABCDEF123456 and sk-proj-XYZ987654321 done"
    out = scrub.redact_text(text)
    assert "sk-ant-api03-ABCDEF123456" not in out
    assert "sk-proj-XYZ987654321" not in out
    assert out.count(scrub.REDACTED) == 2


def test_redacts_auth_headers():
    text = "Authorization: Bearer abcdef.GHIJ-klmno\nx-api-key: secret-token-value"
    out = scrub.redact_text(text)
    assert "abcdef.GHIJ-klmno" not in out
    assert "secret-token-value" not in out


def test_scrub_file_rewrites_in_place(tmp_path):
    p = tmp_path / "session.json"
    p.write_text(json.dumps({"msg": "my key is sk-ant-api03-DEADBEEF00000000"}))
    changed = scrub.scrub_file(p)
    assert changed is True
    assert "sk-ant-api03-DEADBEEF00000000" not in p.read_text()


def test_clean_file_unchanged(tmp_path):
    p = tmp_path / "session.json"
    p.write_text('{"msg": "nothing secret here"}')
    assert scrub.scrub_file(p) is False
