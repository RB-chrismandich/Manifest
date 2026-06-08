from pathlib import Path
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
