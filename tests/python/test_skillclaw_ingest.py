from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_ingest as ing  # noqa: E402


def test_normalize_string_content():
    blocks = ing.normalize_content("hello world")
    assert blocks == [{"kind": "text", "text": "hello world"}]


def test_normalize_block_list_keeps_text_thinking_tooluse():
    content = [
        {"type": "text", "text": "I'll run it"},
        {"type": "thinking", "thinking": "reasoning here", "signature": "SIG"},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
    ]
    blocks = ing.normalize_content(content)
    assert {"kind": "text", "text": "I'll run it"} in blocks
    assert {"kind": "thinking", "text": "reasoning here"} in blocks
    tu = [b for b in blocks if b["kind"] == "tool_use"][0]
    assert tu["name"] == "Bash"
    assert tu["input"] == {"command": "ls"}
    assert all("signature" not in b for b in blocks)


def test_normalize_drops_empty_thinking():
    blocks = ing.normalize_content([{"type": "thinking", "thinking": "", "signature": "X"}])
    assert blocks == []


def test_normalize_structured_tool_result_truncation_is_accurate():
    # Non-string tool_result content must be JSON-serialized then truncated by
    # _truncate (not pre-sliced), so the truncated flag + tail marker stay honest.
    big = {"rows": ["y" * 1000]}
    blocks = ing.normalize_content(
        [{"type": "tool_result", "content": big, "is_error": False}],
        max_tool_output_chars=500,
    )
    tr = blocks[0]
    assert tr["kind"] == "tool_result"
    assert tr["truncated"] is True
    assert "truncated" in tr["output"]


def test_tool_result_output_is_truncated():
    big = "x" * 5000
    blocks = ing.normalize_content(
        [{"type": "tool_result", "content": big, "is_error": False}],
        max_tool_output_chars=500,
    )
    tr = blocks[0]
    assert tr["kind"] == "tool_result"
    assert tr["truncated"] is True
    assert len(tr["output"]) < 600           # 500 + marker, not 5000
    assert "truncated" in tr["output"]


def test_long_tool_use_input_values_are_truncated():
    blocks = ing.normalize_content(
        [{"type": "tool_use", "name": "Write",
          "input": {"file_path": "/a.txt", "content": "y" * 5000}}],
        max_tool_output_chars=500,
    )
    tu = blocks[0]
    assert tu["name"] == "Write"
    assert len(tu["input"]["content"]) < 600
    assert tu["input"]["file_path"] == "/a.txt"   # short values untouched


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_parse_transcript_builds_session(tmp_path):
    f = tmp_path / "sess-abc.jsonl"
    _write_jsonl(f, [
        {"type": "queue-operation", "operation": "enqueue"},   # noise, ignored
        {"type": "user", "sessionId": "sess-abc", "cwd": "/repo", "gitBranch": "main",
         "message": {"role": "user", "content": "fix the bug"}},
        {"type": "assistant", "sessionId": "sess-abc",
         "message": {"role": "assistant",
                     "content": [{"type": "text", "text": "done"}]}},
    ])
    rec = ing.parse_transcript(f)
    assert rec["session_id"] == "sess-abc"
    assert rec["cwd"] == "/repo"
    assert rec["git_branch"] == "main"
    assert len(rec["turns"]) == 2
    assert rec["turns"][0] == {"role": "user", "blocks": [{"kind": "text", "text": "fix the bug"}]}


def test_parse_transcript_tolerates_partial_trailing_line(tmp_path):
    f = tmp_path / "sess-x.jsonl"
    f.write_text(
        json.dumps({"type": "user", "sessionId": "sess-x",
                    "message": {"role": "user", "content": "hi"}}) + "\n"
        + '{"type":"assistant","message":{"role":"assist'   # truncated, no newline
    )
    rec = ing.parse_transcript(f)        # must not raise
    assert rec["session_id"] == "sess-x"
    assert len(rec["turns"]) == 1


def test_parse_transcript_returns_none_when_no_turns(tmp_path):
    f = tmp_path / "empty.jsonl"
    _write_jsonl(f, [{"type": "queue-operation"}, {"type": "attachment"}])
    assert ing.parse_transcript(f) is None


def test_within_window():
    now = 1_000_000.0
    day = 86400
    assert ing.within_window(now - 5 * day, now, window_days=30) is True
    assert ing.within_window(now - 40 * day, now, window_days=30) is False


def test_is_settled():
    now = 1_000_000.0
    assert ing.is_settled(now - 600, now, settle_minutes=5) is True    # 10 min old
    assert ing.is_settled(now - 60, now, settle_minutes=5) is False    # 1 min old
