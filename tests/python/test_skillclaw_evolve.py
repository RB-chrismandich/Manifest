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


def test_evolve_empty_sessions_with_run_id_emits_stage_start(tmp_path, monkeypatch):
    # Even with no sessions, a run_id must produce a stage_start so --status shows
    # evolve ran (and skipped) instead of leaving a stale prior stage in status.json.
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path / "audit"))
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    template = tmp_path / "tpl.md"
    template.write_text("{{LIBRARY}}{{SESSIONS}}")
    evolved = tmp_path / "evolved"
    calls = []
    summary = ev.evolve(sessions_dir, evolved, template, token_budget=100_000,
                        runner=lambda p: calls.append(p) or "NO_SKILLS",
                        run_id="20260609T230501Z-4821")
    assert summary["candidates"] == 0
    assert calls == []                 # no sessions -> still no model calls
    status = json.loads((tmp_path / "audit" / "status.json").read_text())
    assert status["stage"] == "evolve"
    assert status["evolve"]["total"] == 0


def test_evolve_shows_committed_library_not_output_dir(tmp_path):
    # The model must see the REAL committed library (so it doesn't re-propose
    # already-merged skills), not the evolved output dir.
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.json").write_text(json.dumps(
        {"session_id": "s1", "turns": [
            {"role": "user", "blocks": [{"kind": "text", "text": "do thing"}]}]}))
    committed = tmp_path / "committed"
    (committed / "already-merged").mkdir(parents=True)
    (committed / "already-merged" / "SKILL.md").write_text("---\nname: already-merged\n---\n")
    template = tmp_path / "tpl.md"
    template.write_text("LIB {{LIBRARY}} SESS {{SESSIONS}}")
    evolved = tmp_path / "evolved"

    seen = {}

    def fake_runner(prompt):
        seen["prompt"] = prompt
        return "NO_SKILLS"

    ev.evolve(sessions_dir, evolved, template, committed_dir=committed,
              token_budget=100_000, runner=fake_runner)
    assert "already-merged" in seen["prompt"]


def test_library_prompt_includes_name_and_description(tmp_path):
    # FR-005 / contracts/library-prompt.md: {{LIBRARY}} lines are
    # "- <name> — <description>" so the model can match by purpose, not name.
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.json").write_text(json.dumps(
        {"session_id": "s1", "turns": [
            {"role": "user", "blocks": [{"kind": "text", "text": "do thing"}]}]}))
    committed = tmp_path / "committed"
    (committed / "fix-pr-comments").mkdir(parents=True)
    (committed / "fix-pr-comments" / "SKILL.md").write_text(
        "---\nname: fix-pr-comments\ndescription: Fetch, triage and resolve PR review comments.\n---\nbody\n")
    template = tmp_path / "tpl.md"
    template.write_text("LIB {{LIBRARY}} SESS {{SESSIONS}}")

    seen = {}
    ev.evolve(sessions_dir, tmp_path / "evolved", template, committed_dir=committed,
              token_budget=100_000, runner=lambda p: seen.__setitem__("p", p) or "NO_SKILLS")
    assert "- fix-pr-comments — Fetch, triage and resolve PR review comments." in seen["p"]


def test_library_prompt_broken_frontmatter_falls_back_to_name_only(tmp_path):
    # Fail-open: unparsable frontmatter yields a name-only line, never an error.
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.json").write_text(json.dumps(
        {"session_id": "s1", "turns": [
            {"role": "user", "blocks": [{"kind": "text", "text": "x"}]}]}))
    committed = tmp_path / "committed"
    (committed / "broken-skill").mkdir(parents=True)
    (committed / "broken-skill" / "SKILL.md").write_text("no frontmatter here\n")
    template = tmp_path / "tpl.md"
    template.write_text("LIB {{LIBRARY}} SESS {{SESSIONS}}")

    seen = {}
    ev.evolve(sessions_dir, tmp_path / "evolved", template, committed_dir=committed,
              token_budget=100_000, runner=lambda p: seen.__setitem__("p", p) or "NO_SKILLS")
    assert "- broken-skill" in seen["p"]       # present, name-only
    assert "- broken-skill —" not in seen["p"]


def test_library_prompt_truncates_long_descriptions(tmp_path):
    # Descriptions are flattened + truncated at 200 chars to bound prompt cost.
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s1.json").write_text(json.dumps(
        {"session_id": "s1", "turns": [
            {"role": "user", "blocks": [{"kind": "text", "text": "x"}]}]}))
    committed = tmp_path / "committed"
    (committed / "long-skill").mkdir(parents=True)
    long_desc = "verbose " * 60   # ~480 chars, multi-word
    (committed / "long-skill" / "SKILL.md").write_text(
        f"---\nname: long-skill\ndescription: {long_desc}\n---\nbody\n")
    template = tmp_path / "tpl.md"
    template.write_text("LIB\n{{LIBRARY}}\nSESS {{SESSIONS}}")

    seen = {}
    ev.evolve(sessions_dir, tmp_path / "evolved", template, committed_dir=committed,
              token_budget=100_000, runner=lambda p: seen.__setitem__("p", p) or "NO_SKILLS")
    line = [ln for ln in seen["p"].splitlines() if ln.startswith("- long-skill")][0]
    assert len(line) <= 220        # "- long-skill — " prefix + 200-char cap


def test_evolve_multichunk_dedupes_candidates_by_name(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    big = "x" * 160_000  # each session ~40k tokens -> 2 sessions force 2 chunks at budget 50k
    for i in range(2):
        (sessions_dir / f"s{i}.json").write_text(json.dumps(
            {"session_id": f"s{i}", "turns": [
                {"role": "user", "blocks": [{"kind": "text", "text": big}]}]}))
    template = tmp_path / "tpl.md"
    template.write_text("{{LIBRARY}}{{SESSIONS}}")
    evolved = tmp_path / "evolved"

    # both chunks emit the same-named skill -> reduce must dedupe to one
    out = ("~~~skill name=dup\n---\nname: dup\ndescription: d\n---\n# Dup\nstep\n~~~\n")
    summary = ev.evolve(sessions_dir, evolved, template, token_budget=50_000,
                        runner=lambda p: out)
    assert summary["chunks"] >= 2
    assert summary["candidates"] == 1
    assert summary["written"] == ["dup"]


def test_evolve_emits_chunk_events_to_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path / "audit"))
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    big = "x" * 160_000  # ~40k tokens each -> 2 sessions force >=2 chunks at budget 50k
    for i in range(2):
        (sessions_dir / f"s{i}.json").write_text(json.dumps(
            {"session_id": f"s{i}", "turns": [
                {"role": "user", "blocks": [{"kind": "text", "text": big}]}]}))
    template = tmp_path / "tpl.md"
    template.write_text("{{LIBRARY}}{{SESSIONS}}")
    evolved = tmp_path / "evolved"
    out = "~~~skill name=dup\n---\nname: dup\ndescription: d\n---\n# Dup\nstep\n~~~\n"

    ev.evolve(sessions_dir, evolved, template, token_budget=50_000,
              runner=lambda p: out, run_id="20260609T230501Z-4821")

    log_lines = (tmp_path / "audit" / "promote.log").read_text().splitlines()
    events = [json.loads(ln)["event"] for ln in log_lines]
    assert "stage_start" in events
    assert events.count("chunk_done") >= 2
    status = json.loads((tmp_path / "audit" / "status.json").read_text())
    assert status["evolve"]["total"] >= 2
    assert status["evolve"]["chunk"] == status["evolve"]["total"]  # last chunk recorded

    chunk_events = [json.loads(ln) for ln in log_lines
                    if json.loads(ln)["event"] == "chunk_done"]
    for e in chunk_events:
        assert e["chunk_seconds"] <= e["elapsed_s"] + 1e-9   # delta never exceeds cumulative
    elapsed_values = [e["elapsed_s"] for e in chunk_events]
    assert elapsed_values == sorted(elapsed_values)          # cumulative is monotonic
