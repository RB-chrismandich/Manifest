from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_evolve as ev  # noqa: E402

TEMPLATE = "LIB:\n{{LIBRARY}}\nSESS:\n{{SESSIONS}}\n"


def test_estimate_tokens_is_roughly_quarter_length():
    assert ev.estimate_tokens("a" * 400) == 100


def test_build_prompt_substitutes_sections():
    sessions = [{"session_id": "s1", "turns": [
        {"role": "user", "blocks": [{"kind": "text", "text": "do x"}]}]}]
    prompt = ev.build_prompt(TEMPLATE, sessions, ["existing-skill"])
    assert "existing-skill" in prompt
    assert "do x" in prompt
    assert "{{LIBRARY}}" not in prompt and "{{SESSIONS}}" not in prompt


def test_parse_candidates_extracts_skill_blocks():
    output = (
        "~~~skill name=foo-bar\n"
        "---\nname: foo-bar\ndescription: does foo\n---\n# Foo\nstep 1\n"
        "~~~\n"
    )
    cands = ev.parse_candidates(output)
    assert cands == [{"name": "foo-bar",
                      "content": "---\nname: foo-bar\ndescription: does foo\n---\n# Foo\nstep 1\n"}]


def test_parse_candidates_handles_no_skills():
    assert ev.parse_candidates("NO_SKILLS") == []
