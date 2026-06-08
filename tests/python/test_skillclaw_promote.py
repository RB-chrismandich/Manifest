import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_promote as promote  # noqa: E402

VALID = "---\nname: foo\ndescription: does foo\n---\n# Foo\nbody\n"


def _skill(dirpath: Path, name: str, body: str) -> Path:
    d = dirpath / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body)
    return d


def test_classify_new_changed_unchanged(tmp_path):
    evolved = tmp_path / "evolved"
    committed = tmp_path / "committed"
    _skill(evolved, "alpha", VALID.replace("foo", "alpha"))            # NEW
    _skill(evolved, "beta", VALID.replace("foo", "beta") + "more\n")   # CHANGED
    _skill(committed, "beta", VALID.replace("foo", "beta"))
    _skill(evolved, "gamma", VALID.replace("foo", "gamma"))            # UNCHANGED
    _skill(committed, "gamma", VALID.replace("foo", "gamma"))

    result = promote.classify(evolved, committed)
    status = {c["name"]: c["status"] for c in result}
    assert status["alpha"] == "NEW"
    assert status["beta"] == "CHANGED"
    assert status["gamma"] == "UNCHANGED"


def test_validate_rejects_missing_frontmatter(tmp_path):
    d = _skill(tmp_path, "bad", "# no frontmatter\n")
    ok, reason = promote.validate_skill(d / "SKILL.md")
    assert ok is False
    assert "frontmatter" in reason.lower()


def test_validate_accepts_complete_frontmatter(tmp_path):
    d = _skill(tmp_path, "good", VALID)
    ok, reason = promote.validate_skill(d / "SKILL.md")
    assert ok is True
    assert reason == ""


def test_main_emits_promotable_json(tmp_path, capsys):
    evolved = tmp_path / "evolved"
    committed = tmp_path / "committed"
    _skill(evolved, "alpha", VALID.replace("foo", "alpha"))
    _skill(committed, "_", VALID)  # ensure committed dir exists
    rc = promote.main([str(evolved), str(committed)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in payload["promote"]}
    assert "alpha" in names
