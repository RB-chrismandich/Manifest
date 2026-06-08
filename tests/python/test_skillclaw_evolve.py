from pathlib import Path
import json
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


def test_chunk_sessions_splits_over_budget():
    big = "x" * 160_000
    sessions = [{"session_id": f"s{i}",
                 "turns": [{"role": "user", "blocks": [{"kind": "text", "text": big}]}]}
                for i in range(3)]
    chunks = ev.chunk_sessions(sessions, token_budget=100_000)
    assert len(chunks) >= 2                       # 120k tokens total -> multiple chunks
    assert sum(len(c) for c in chunks) == 3       # no session lost


def test_chunk_sessions_single_chunk_under_budget():
    sessions = [{"session_id": "s1",
                 "turns": [{"role": "user", "blocks": [{"kind": "text", "text": "tiny"}]}]}]
    chunks = ev.chunk_sessions(sessions, token_budget=100_000)
    assert chunks == [sessions]


def test_evolve_uses_injected_runner_and_writes(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.json").write_text(json.dumps(
        {"session_id": "s1", "turns": [
            {"role": "user", "blocks": [{"kind": "text", "text": "deploy steps"}]}]}))
    template = tmp_path / "tpl.md"
    template.write_text("LIB {{LIBRARY}} SESS {{SESSIONS}}")
    evolved = tmp_path / "evolved"

    def fake_runner(prompt):
        assert "deploy steps" in prompt
        return ("~~~skill name=deploy-flow\n---\nname: deploy-flow\n"
                "description: how to deploy\n---\n# Deploy\nstep 1\n~~~\n")

    summary = ev.evolve(sessions_dir, evolved, template, token_budget=100_000,
                        runner=fake_runner)
    assert summary["candidates"] == 1
    assert (evolved / "deploy-flow" / "SKILL.md").read_text().startswith("---")


def test_evolve_empty_sessions_is_clean_noop(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    template = tmp_path / "tpl.md"
    template.write_text("{{LIBRARY}}{{SESSIONS}}")
    evolved = tmp_path / "evolved"
    calls = []
    summary = ev.evolve(sessions_dir, evolved, template, token_budget=100_000,
                        runner=lambda p: calls.append(p) or "NO_SKILLS")
    assert summary["candidates"] == 0
    assert calls == []                 # no sessions -> no model calls
