import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
from skillclaw import ingest as ing


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
    tu = next(b for b in blocks if b["kind"] == "tool_use")
    assert tu["name"] == "Bash"
    assert tu["input"] == {"command": "ls"}
    assert all("signature" not in b for b in blocks)


def test_normalize_drops_empty_thinking():
    blocks = ing.normalize_content(
        [{"type": "thinking", "thinking": "", "signature": "X"}]
    )
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
    assert len(tr["output"]) < 600  # 500 + marker, not 5000
    assert "truncated" in tr["output"]


def test_long_tool_use_input_values_are_truncated():
    blocks = ing.normalize_content(
        [
            {
                "type": "tool_use",
                "name": "Write",
                "input": {"file_path": "/a.txt", "content": "y" * 5000},
            }
        ],
        max_tool_output_chars=500,
    )
    tu = blocks[0]
    assert tu["name"] == "Write"
    assert len(tu["input"]["content"]) < 600
    assert tu["input"]["file_path"] == "/a.txt"  # short values untouched


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_parse_transcript_builds_session(tmp_path):
    f = tmp_path / "sess-abc.jsonl"
    _write_jsonl(
        f,
        [
            {"type": "queue-operation", "operation": "enqueue"},  # noise, ignored
            {
                "type": "user",
                "sessionId": "sess-abc",
                "cwd": "/repo",
                "gitBranch": "main",
                "message": {"role": "user", "content": "fix the bug"},
            },
            {
                "type": "assistant",
                "sessionId": "sess-abc",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                },
            },
        ],
    )
    rec = ing.parse_transcript(f)
    assert rec["session_id"] == "sess-abc"
    assert rec["cwd"] == "/repo"
    assert rec["git_branch"] == "main"
    assert len(rec["turns"]) == 2
    assert rec["turns"][0] == {
        "role": "user",
        "blocks": [{"kind": "text", "text": "fix the bug"}],
    }


def test_parse_transcript_tolerates_partial_trailing_line(tmp_path):
    f = tmp_path / "sess-x.jsonl"
    f.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "sess-x",
                "message": {"role": "user", "content": "hi"},
            }
        )
        + "\n"
        + '{"type":"assistant","message":{"role":"assist'  # truncated, no newline
    )
    rec = ing.parse_transcript(f)  # must not raise
    assert rec["session_id"] == "sess-x"
    assert len(rec["turns"]) == 1


def test_parse_transcript_returns_none_when_no_turns(tmp_path):
    f = tmp_path / "empty.jsonl"
    _write_jsonl(f, [{"type": "queue-operation"}, {"type": "attachment"}])
    assert ing.parse_transcript(f) is None


def test_parse_transcript_skips_plaintext_noise_line(tmp_path):
    f = tmp_path / "sess-noise.jsonl"
    f.write_text(
        "this is not json at all\n"
        + json.dumps(
            {
                "type": "user",
                "sessionId": "sess-noise",
                "message": {"role": "user", "content": "hi"},
            }
        )
        + "\n"
    )
    rec = ing.parse_transcript(f)
    assert rec["session_id"] == "sess-noise"
    assert len(rec["turns"]) == 1
    assert rec["turns"][0]["blocks"] == [{"kind": "text", "text": "hi"}]


def test_parse_transcript_keeps_whitespace_padded_json(tmp_path):
    f = tmp_path / "sess-pad.jsonl"
    padded = "   " + json.dumps(
        {
            "type": "user",
            "sessionId": "sess-pad",
            "message": {"role": "user", "content": "padded"},
        }
    )
    f.write_text(padded + "\n")
    rec = ing.parse_transcript(f)
    assert rec is not None
    assert rec["session_id"] == "sess-pad"
    assert len(rec["turns"]) == 1
    assert rec["turns"][0]["blocks"] == [{"kind": "text", "text": "padded"}]


def test_within_window():
    now = 1_000_000.0
    day = 86400
    assert ing.within_window(now - 5 * day, now, window_days=30) is True
    assert ing.within_window(now - 40 * day, now, window_days=30) is False


def test_is_settled():
    now = 1_000_000.0
    assert ing.is_settled(now - 600, now, settle_minutes=5) is True  # 10 min old
    assert ing.is_settled(now - 60, now, settle_minutes=5) is False  # 1 min old


def _mk_transcript(d, name, mtime):
    f = d / f"{name}.jsonl"
    f.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": name,
                "message": {"role": "user", "content": "hi"},
            }
        )
        + "\n"
    )
    import os

    os.utime(f, (mtime, mtime))
    return f


def test_ingest_writes_and_filters(tmp_path):
    src = tmp_path / "projects" / "repo"
    src.mkdir(parents=True)
    out = tmp_path / "sessions"
    state = tmp_path / ".state.json"
    now = 1_000_000.0
    _mk_transcript(src, "fresh", now - 3600)  # 1h old -> ingested
    _mk_transcript(src, "stale", now - 50 * 86400)  # 50d old -> window-skipped
    _mk_transcript(src, "active", now - 60)  # 1m old -> settle-skipped

    summary = ing.ingest(
        tmp_path / "projects",
        out,
        state,
        window_days=30,
        settle_minutes=5,
        max_tool_output_chars=500,
        now=now,
    )
    assert summary["ingested"] == 1
    assert summary["skipped_old"] == 1
    assert summary["skipped_unsettled"] == 1
    assert (out / "fresh.json").exists()


def test_ingest_is_incremental(tmp_path):
    src = tmp_path / "projects" / "repo"
    src.mkdir(parents=True)
    out = tmp_path / "sessions"
    state = tmp_path / ".state.json"
    now = 1_000_000.0
    _mk_transcript(src, "one", now - 3600)
    first = ing.ingest(
        tmp_path / "projects",
        out,
        state,
        window_days=30,
        settle_minutes=5,
        max_tool_output_chars=500,
        now=now,
    )
    assert first["ingested"] == 1
    second = ing.ingest(
        tmp_path / "projects",
        out,
        state,
        window_days=30,
        settle_minutes=5,
        max_tool_output_chars=500,
        now=now,
    )
    assert second["ingested"] == 0
    assert second["skipped_seen"] == 1
