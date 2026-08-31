# SkillClaw Proxy-Free Evolve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SkillClaw's Max-incompatible inline capture proxy with passive ingestion of Claude Code JSONL transcripts feeding the existing PR-gated evolve/promote pipeline, with `claude -p` (Max-backed) as the distillation engine.

**Architecture:** Two new Python scripts (`skillclaw_ingest.py`, `skillclaw_evolve.py`) plus a prompt template replace the dead proxy+daemon. Ingest parses `~/.claude/projects/**/*.jsonl` into scrubbed, noise-stripped session JSON; evolve map-reduces those sessions through `claude -p` into `SKILL.md` candidates; the existing `skillclaw_promote.{py,sh}` classify→PR-gate machinery runs unchanged except for swapping the evolve call and surfacing rejected candidates. The proxy stack (daemon, launchd unit, shell wrappers) is removed from `bootstrap/lib/skillclaw.sh`.

**Tech Stack:** Python 3 (stdlib only: `json`, `re`, `pathlib`, `argparse`, `subprocess`, `time`), Bash, pytest, bats, PyYAML (already a dependency).

---

## Reference: real transcript schema (verified against live data)

Each line in `~/.claude/projects/<slug>/<sessionId>.jsonl` is one JSON object. Only `type: "user"` and `type: "assistant"` carry conversation; other types (`queue-operation`, `attachment`, `last-prompt`) are noise and ignored.

```jsonc
{"type":"user","sessionId":"...","timestamp":"...","cwd":"...","gitBranch":"...",
 "message":{"role":"user","content": "<str>" OR [ <blocks> ]}}
```

`message.content` is either a string or a list of blocks:
- `{"type":"text","text":"..."}` — assistant/user text (keep)
- `{"type":"thinking","thinking":"...","signature":"..."}` — reasoning (keep `thinking` if non-empty; drop `signature`)
- `{"type":"tool_use","id":"...","name":"Bash","input":{...}}` — keep `name` + `input` (truncate long string values)
- `{"type":"tool_result","tool_use_id":"...","content":"...","is_error":false}` — **truncate `content`** (primary noise source)

The filename stem is the `sessionId`. File `mtime` is used for window/settle decisions.

---

## File Structure

**Create:**
- `configs/claude/scripts/skillclaw_ingest.py` — transcript → normalized session JSON (stripping, window, settle, incremental state)
- `configs/claude/scripts/skillclaw_evolve.py` — sessions → `SKILL.md` candidates via `claude -p` (map-reduce)
- `configs/claude/prompts/skillclaw_evolve.md` — distillation prompt template
- `tests/python/test_skillclaw_ingest.py`
- `tests/python/test_skillclaw_evolve.py`

**Modify:**
- `configs/claude/scripts/skillclaw_promote.py` — copy rejected candidates to `rejected/`
- `configs/claude/scripts/skillclaw_promote.sh` — call `skillclaw_evolve.py`; warn on rejected
- `configs/claude/config/skillclaw.yml` — drop proxy/capture; add ingest/evolve knobs
- `bootstrap/lib/skillclaw.sh` — remove proxy/daemon/wrappers/supervisor; redefine enable/disable
- `tests/python/test_skillclaw_promote.py` — rejected-dir test
- `tests/bats/skillclaw_promote.bats` — assert new evolve call + rejected warning
- `tests/bats/skillclaw_lib.bats`, `tests/bats/skillclaw_config.bats` — drop proxy/daemon assertions
- `docs/SKILLCLAW.md` — rewrite for proxy-free model + annexation

**Module API contract** (names used consistently across tasks):

```python
# skillclaw_ingest.py
normalize_content(content, max_tool_output_chars=500) -> list[dict]   # blocks
parse_transcript(path, max_tool_output_chars=500) -> dict | None      # session record
within_window(mtime, now, window_days) -> bool
is_settled(mtime, now, settle_minutes) -> bool
load_state(state_path) -> dict
save_state(state_path, state) -> None
ingest(transcripts_dir, out_dir, state_path, *, window_days, settle_minutes,
       max_tool_output_chars, now) -> dict                            # summary counts
main(argv) -> int

# skillclaw_evolve.py
estimate_tokens(text) -> int                                         # len//4 heuristic
load_sessions(sessions_dir) -> list[dict]
build_prompt(template, sessions, library_names) -> str
chunk_sessions(sessions, token_budget) -> list[list[dict]]
run_claude(prompt, *, runner=subprocess_runner) -> str               # injectable runner
parse_candidates(model_output) -> list[dict]                         # [{name, content}]
write_candidates(candidates, evolved_dir) -> list[str]
evolve(sessions_dir, evolved_dir, template_path, *, token_budget, runner) -> dict
main(argv) -> int
```

The injectable `runner` in `run_claude` is how tests avoid invoking the real `claude` CLI.

---

## Task 1: Ingest — normalize message content into blocks

**Files:**
- Create: `configs/claude/scripts/skillclaw_ingest.py`
- Test: `tests/python/test_skillclaw_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/python/test_skillclaw_ingest.py
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
    # signature must never survive
    assert all("signature" not in b for b in blocks)


def test_normalize_drops_empty_thinking():
    blocks = ing.normalize_content([{"type": "thinking", "thinking": "", "signature": "X"}])
    assert blocks == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'skillclaw_ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# configs/claude/scripts/skillclaw_ingest.py
#!/usr/bin/env python3
"""Ingest Claude Code transcripts into scrubbed, noise-stripped session JSON.

Passive replacement for the retired SkillClaw capture proxy. Reads
~/.claude/projects/**/*.jsonl, normalizes conversation turns, truncates noisy
tool payloads, filters by recency, skips still-being-written files, and tracks
processed sessions incrementally.

Usage:
    skillclaw_ingest.py <transcripts_dir> <out_dir> [--state FILE]
        [--window-days N] [--settle-minutes N] [--max-tool-output-chars N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

DEFAULT_MAX_TOOL_OUTPUT = 500


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"…[+{len(text) - limit} chars truncated]", True


def normalize_content(content, max_tool_output_chars: int = DEFAULT_MAX_TOOL_OUTPUT) -> list[dict]:
    """Normalize a message.content (str or block list) into kept blocks."""
    if isinstance(content, str):
        return [{"kind": "text", "text": content}] if content.strip() else []
    if not isinstance(content, list):
        return []
    out: list[dict] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            txt = block.get("text", "")
            if txt.strip():
                out.append({"kind": "text", "text": txt})
        elif bt == "thinking":
            txt = block.get("thinking", "")
            if txt.strip():
                out.append({"kind": "thinking", "text": txt})
        elif bt == "tool_use":
            out.append({"kind": "tool_use", "name": block.get("name", "?"),
                        "input": block.get("input", {})})
        elif bt == "tool_result":
            raw = block.get("content", "")
            if not isinstance(raw, str):
                raw = json.dumps(raw)[:max_tool_output_chars]
            text, truncated = _truncate(raw, max_tool_output_chars)
            out.append({"kind": "tool_result", "output": text,
                        "is_error": bool(block.get("is_error", False)),
                        "truncated": truncated})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_ingest.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_ingest.py tests/python/test_skillclaw_ingest.py
git commit -m "feat(skillclaw): ingest normalize_content — block extraction + thinking-signature drop"
```

---

## Task 2: Ingest — truncate noisy tool payloads (stdout, base64, large tool_use input)

**Files:**
- Modify: `configs/claude/scripts/skillclaw_ingest.py`
- Test: `tests/python/test_skillclaw_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_ingest.py::test_long_tool_use_input_values_are_truncated -v`
Expected: FAIL — `tool_use.input.content` is the full 5000-char string.

- [ ] **Step 3: Write minimal implementation**

Replace the `tool_use` branch in `normalize_content` with one that truncates long string values:

```python
        elif bt == "tool_use":
            raw_input = block.get("input", {})
            trimmed = {}
            if isinstance(raw_input, dict):
                for k, v in raw_input.items():
                    if isinstance(v, str):
                        trimmed[k] = _truncate(v, max_tool_output_chars)[0]
                    else:
                        trimmed[k] = v
            else:
                trimmed = raw_input
            out.append({"kind": "tool_use", "name": block.get("name", "?"),
                        "input": trimmed})
```

(The `tool_result` truncation from Task 1 already satisfies `test_tool_result_output_is_truncated`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_ingest.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_ingest.py tests/python/test_skillclaw_ingest.py
git commit -m "feat(skillclaw): ingest truncates noisy tool_result + tool_use input payloads"
```

---

## Task 3: Ingest — parse a full transcript into a session record

**Files:**
- Modify: `configs/claude/scripts/skillclaw_ingest.py`
- Test: `tests/python/test_skillclaw_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


import json  # noqa: E402  (top of file already has pathlib/sys)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_ingest.py::test_parse_transcript_builds_session -v`
Expected: FAIL — `parse_transcript` not defined.

- [ ] **Step 3: Write minimal implementation**

Append to `skillclaw_ingest.py`:

```python
def parse_transcript(path: Path, max_tool_output_chars: int = DEFAULT_MAX_TOOL_OUTPUT) -> dict | None:
    """Parse one transcript .jsonl into a session record, or None if no turns.

    Defensive: skips unparseable lines (including a truncated trailing line from
    a still-active session) rather than raising.
    """
    session_id = path.stem
    cwd = git_branch = None
    turns: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # partial/corrupt line — skip
            if obj.get("type") not in ("user", "assistant"):
                continue
            session_id = obj.get("sessionId", session_id)
            cwd = obj.get("cwd", cwd)
            git_branch = obj.get("gitBranch", git_branch)
            msg = obj.get("message", {})
            blocks = normalize_content(msg.get("content"), max_tool_output_chars)
            if blocks:
                turns.append({"role": msg.get("role", "?"), "blocks": blocks})
    if not turns:
        return None
    return {"session_id": session_id, "cwd": cwd, "git_branch": git_branch, "turns": turns}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_ingest.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_ingest.py tests/python/test_skillclaw_ingest.py
git commit -m "feat(skillclaw): ingest parse_transcript — turn extraction, partial-line tolerance"
```

---

## Task 4: Ingest — window + settle predicates

**Files:**
- Modify: `configs/claude/scripts/skillclaw_ingest.py`
- Test: `tests/python/test_skillclaw_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
def test_within_window():
    now = 1_000_000.0
    day = 86400
    assert ing.within_window(now - 5 * day, now, window_days=30) is True
    assert ing.within_window(now - 40 * day, now, window_days=30) is False


def test_is_settled():
    now = 1_000_000.0
    assert ing.is_settled(now - 600, now, settle_minutes=5) is True    # 10 min old
    assert ing.is_settled(now - 60, now, settle_minutes=5) is False    # 1 min old
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_ingest.py::test_within_window -v`
Expected: FAIL — `within_window` not defined.

- [ ] **Step 3: Write minimal implementation**

Append to `skillclaw_ingest.py`:

```python
def within_window(mtime: float, now: float, window_days: int) -> bool:
    """True if mtime falls within the last window_days from now."""
    return (now - mtime) <= window_days * 86400


def is_settled(mtime: float, now: float, settle_minutes: int) -> bool:
    """True if the file has been idle long enough to be safely read."""
    return (now - mtime) >= settle_minutes * 60
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_ingest.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_ingest.py tests/python/test_skillclaw_ingest.py
git commit -m "feat(skillclaw): ingest window + settle recency predicates"
```

---

## Task 5: Ingest — orchestration, incremental state, CLI

**Files:**
- Modify: `configs/claude/scripts/skillclaw_ingest.py`
- Test: `tests/python/test_skillclaw_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
def _mk_transcript(d: Path, name: str, mtime: float) -> Path:
    f = d / f"{name}.jsonl"
    f.write_text(json.dumps({"type": "user", "sessionId": name,
                             "message": {"role": "user", "content": "hi"}}) + "\n")
    import os
    os.utime(f, (mtime, mtime))
    return f


def test_ingest_writes_and_filters(tmp_path):
    src = tmp_path / "projects" / "repo"
    src.mkdir(parents=True)
    out = tmp_path / "sessions"
    state = tmp_path / ".state.json"
    now = 1_000_000.0
    _mk_transcript(src, "fresh", now - 3600)            # 1h old → ingested
    _mk_transcript(src, "stale", now - 50 * 86400)      # 50d old → window-skipped
    _mk_transcript(src, "active", now - 60)             # 1m old → settle-skipped

    summary = ing.ingest(tmp_path / "projects", out, state,
                         window_days=30, settle_minutes=5,
                         max_tool_output_chars=500, now=now)
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
    first = ing.ingest(tmp_path / "projects", out, state, window_days=30,
                       settle_minutes=5, max_tool_output_chars=500, now=now)
    assert first["ingested"] == 1
    second = ing.ingest(tmp_path / "projects", out, state, window_days=30,
                        settle_minutes=5, max_tool_output_chars=500, now=now)
    assert second["ingested"] == 0
    assert second["skipped_seen"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_ingest.py::test_ingest_writes_and_filters -v`
Expected: FAIL — `ingest` not defined.

- [ ] **Step 3: Write minimal implementation**

Append to `skillclaw_ingest.py`:

```python
def load_state(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ingest(transcripts_dir, out_dir, state_path, *, window_days, settle_minutes,
           max_tool_output_chars, now=None) -> dict:
    """Ingest new, settled, in-window transcripts into out_dir. Returns counts."""
    now = time.time() if now is None else now
    transcripts_dir = Path(transcripts_dir).expanduser()
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(state_path).expanduser()
    state = load_state(state_path)

    summary = {"ingested": 0, "skipped_old": 0, "skipped_unsettled": 0,
               "skipped_seen": 0, "skipped_empty": 0}
    for f in sorted(transcripts_dir.rglob("*.jsonl")):
        mtime = f.stat().st_mtime
        if not within_window(mtime, now, window_days):
            summary["skipped_old"] += 1
            continue
        if not is_settled(mtime, now, settle_minutes):
            summary["skipped_unsettled"] += 1
            continue
        key = str(f)
        if state.get(key) == mtime:
            summary["skipped_seen"] += 1
            continue
        rec = parse_transcript(f, max_tool_output_chars)
        if rec is None:
            summary["skipped_empty"] += 1
            state[key] = mtime
            continue
        (out_dir / f"{rec['session_id']}.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
        state[key] = mtime
        summary["ingested"] += 1
    save_state(state_path, state)
    return summary


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--state", default="~/.skillclaw/.ingest-state.json")
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--settle-minutes", type=int, default=5)
    ap.add_argument("--max-tool-output-chars", type=int, default=DEFAULT_MAX_TOOL_OUTPUT)
    args = ap.parse_args(argv)
    summary = ingest(args.transcripts_dir, args.out_dir, args.state,
                     window_days=args.window_days, settle_minutes=args.settle_minutes,
                     max_tool_output_chars=args.max_tool_output_chars)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_ingest.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_ingest.py tests/python/test_skillclaw_ingest.py
git commit -m "feat(skillclaw): ingest orchestration with incremental state + CLI"
```

---

## Task 6: Evolve — prompt template + single-pass distillation

**Files:**
- Create: `configs/claude/prompts/skillclaw_evolve.md`
- Create: `configs/claude/scripts/skillclaw_evolve.py`
- Test: `tests/python/test_skillclaw_evolve.py`

- [ ] **Step 1: Write the prompt template (not code — content step)**

```markdown
<!-- configs/claude/prompts/skillclaw_evolve.md -->
# SkillClaw Distillation Prompt

You are distilling reusable Claude Code **skills** from real agent sessions.

A skill is a `SKILL.md` file with YAML frontmatter (`name`, `description`) and a
markdown body describing a repeatable procedure the agent should follow.

## Existing skill library (do NOT duplicate these names unless improving them)

{{LIBRARY}}

## Sessions (scrubbed, noise-truncated)

{{SESSIONS}}

## Your task

Identify recurring, generalizable workflows in these sessions that are NOT already
well covered by the existing library. For each, emit one skill.

Output ONLY a sequence of skill blocks in this exact fenced format, nothing else:

~~~skill name=<kebab-case-name>
---
name: <kebab-case-name>
description: <one line: when to use this skill>
---
# <Title>

<body: numbered, concrete steps>
~~~

If nothing rises to a reusable skill, output the single line: NO_SKILLS
```

- [ ] **Step 2: Write the failing test**

```python
# tests/python/test_skillclaw_evolve.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_evolve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skillclaw_evolve'`

- [ ] **Step 4: Write minimal implementation**

```python
# configs/claude/scripts/skillclaw_evolve.py
#!/usr/bin/env python3
"""Distill SKILL.md candidates from ingested sessions via `claude -p` (Max-backed).

Replaces the retired `skillclaw evolve` binary. Map-reduces sessions through the
headless Claude CLI: chunks that exceed the token budget are distilled
independently (map), then merged (reduce). No proxy, no API key.

Usage:
    skillclaw_evolve.py <sessions_dir> <evolved_dir> [--template FILE]
        [--token-budget N]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_TOKEN_BUDGET = 100_000
_SKILL_RE = re.compile(r"~~~skill name=(?P<name>[^\n]+)\n(?P<body>.*?)~~~", re.DOTALL)


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars per token."""
    return len(text) // 4


def _render_session(s: dict) -> str:
    lines = [f"### session {s.get('session_id', '?')}"]
    for turn in s.get("turns", []):
        for b in turn["blocks"]:
            if b["kind"] in ("text", "thinking"):
                lines.append(f"[{turn['role']}/{b['kind']}] {b['text']}")
            elif b["kind"] == "tool_use":
                lines.append(f"[tool_use {b['name']}] {json.dumps(b['input'])}")
            elif b["kind"] == "tool_result":
                lines.append(f"[tool_result err={b['is_error']}] {b['output']}")
    return "\n".join(lines)


def load_sessions(sessions_dir) -> list[dict]:
    sessions_dir = Path(sessions_dir).expanduser()
    out = []
    for f in sorted(sessions_dir.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def build_prompt(template: str, sessions: list[dict], library_names: list[str]) -> str:
    library = "\n".join(f"- {n}" for n in library_names) or "(empty)"
    rendered = "\n\n".join(_render_session(s) for s in sessions) or "(none)"
    return template.replace("{{LIBRARY}}", library).replace("{{SESSIONS}}", rendered)


def parse_candidates(output: str) -> list[dict]:
    return [{"name": m.group("name").strip(), "content": m.group("body")}
            for m in _SKILL_RE.finditer(output)]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_evolve.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/skillclaw_evolve.py configs/claude/prompts/skillclaw_evolve.md tests/python/test_skillclaw_evolve.py
git commit -m "feat(skillclaw): evolve prompt template + token estimate, prompt build, candidate parse"
```

---

## Task 7: Evolve — map-reduce chunking

**Files:**
- Modify: `configs/claude/scripts/skillclaw_evolve.py`
- Test: `tests/python/test_skillclaw_evolve.py`

- [ ] **Step 1: Write the failing test**

```python
def test_chunk_sessions_splits_over_budget():
    # each session renders to ~ (len//4) tokens; make 3 sessions of ~40k tokens
    big = "x" * 160_000
    sessions = [{"session_id": f"s{i}",
                 "turns": [{"role": "user", "blocks": [{"kind": "text", "text": big}]}]}
                for i in range(3)]
    chunks = ev.chunk_sessions(sessions, token_budget=100_000)
    assert len(chunks) >= 2                       # 120k tokens total → multiple chunks
    assert sum(len(c) for c in chunks) == 3       # no session lost


def test_chunk_sessions_single_chunk_under_budget():
    sessions = [{"session_id": "s1",
                 "turns": [{"role": "user", "blocks": [{"kind": "text", "text": "tiny"}]}]}]
    chunks = ev.chunk_sessions(sessions, token_budget=100_000)
    assert chunks == [sessions]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_evolve.py::test_chunk_sessions_splits_over_budget -v`
Expected: FAIL — `chunk_sessions` not defined.

- [ ] **Step 3: Write minimal implementation**

Append to `skillclaw_evolve.py`:

```python
def chunk_sessions(sessions: list[dict], token_budget: int) -> list[list[dict]]:
    """Greedily pack sessions into chunks whose rendered size stays under budget.

    A single session larger than the budget gets its own chunk (it cannot be
    split further here; the renderer already truncated tool noise upstream).
    """
    if not sessions:
        return []
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0
    for s in sessions:
        cost = estimate_tokens(_render_session(s))
        if current and current_tokens + cost > token_budget:
            chunks.append(current)
            current, current_tokens = [], 0
        current.append(s)
        current_tokens += cost
    if current:
        chunks.append(current)
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_evolve.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_evolve.py tests/python/test_skillclaw_evolve.py
git commit -m "feat(skillclaw): evolve map-reduce chunking under token budget"
```

---

## Task 8: Evolve — runner injection, evolve(), write candidates, CLI

**Files:**
- Modify: `configs/claude/scripts/skillclaw_evolve.py`
- Test: `tests/python/test_skillclaw_evolve.py`

- [ ] **Step 1: Write the failing test**

```python
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
    assert calls == []                 # no sessions → no model calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_evolve.py::test_evolve_uses_injected_runner_and_writes -v`
Expected: FAIL — `evolve` not defined.

- [ ] **Step 3: Write minimal implementation**

Append to `skillclaw_evolve.py`:

```python
def subprocess_runner(prompt: str) -> str:
    """Default runner: invoke headless `claude -p` (Max-backed)."""
    proc = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {proc.stderr.strip()}")
    return proc.stdout


def write_candidates(candidates: list[dict], evolved_dir: Path) -> list[str]:
    evolved_dir = Path(evolved_dir).expanduser()
    written = []
    for c in candidates:
        d = evolved_dir / c["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(c["content"], encoding="utf-8")
        written.append(c["name"])
    return written


def _committed_library_names(evolved_dir: Path) -> list[str]:
    base = Path(evolved_dir).expanduser()
    return sorted(p.parent.name for p in base.glob("*/SKILL.md")) if base.exists() else []


def evolve(sessions_dir, evolved_dir, template_path, *,
           token_budget=DEFAULT_TOKEN_BUDGET, runner=subprocess_runner) -> dict:
    """Map-reduce sessions into SKILL.md candidates. Returns a summary dict."""
    sessions = load_sessions(sessions_dir)
    template = Path(template_path).expanduser().read_text(encoding="utf-8")
    library = _committed_library_names(evolved_dir)
    if not sessions:
        return {"candidates": 0, "chunks": 0, "written": []}

    chunks = chunk_sessions(sessions, token_budget)
    mapped: list[dict] = []
    for chunk in chunks:
        out = runner(build_prompt(template, chunk, library))
        mapped.extend(parse_candidates(out))

    # reduce: dedupe by name (last write wins); a single chunk skips a 2nd call
    if len(chunks) > 1 and mapped:
        names = {c["name"] for c in mapped}
        deduped = {}
        for c in mapped:
            deduped[c["name"]] = c
        mapped = list(deduped.values())
        _ = names  # reduction is name-dedupe; cross-chunk merge stays simple in V1

    written = write_candidates(mapped, evolved_dir)
    return {"candidates": len(written), "chunks": len(chunks), "written": written}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions_dir")
    ap.add_argument("evolved_dir")
    ap.add_argument("--template", default="~/.claude/prompts/skillclaw_evolve.md")
    ap.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    args = ap.parse_args(argv)
    try:
        summary = evolve(args.sessions_dir, args.evolved_dir, args.template,
                         token_budget=args.token_budget)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"skillclaw_evolve: {e}", file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_evolve.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_evolve.py tests/python/test_skillclaw_evolve.py
git commit -m "feat(skillclaw): evolve() map-reduce orchestration + claude -p runner + CLI"
```

---

## Task 9: Promote — surface rejected candidates instead of dropping silently

**Files:**
- Modify: `configs/claude/scripts/skillclaw_promote.py:69-97` (the `main` body)
- Test: `tests/python/test_skillclaw_promote.py`

- [ ] **Step 1: Write the failing test**

```python
def test_rejected_candidates_are_copied_to_rejected_dir(tmp_path):
    evolved = tmp_path / "evolved"
    committed = tmp_path / "committed"
    rejected = tmp_path / "rejected"
    _skill(committed, "_", VALID)                       # committed dir exists
    _skill(evolved, "broken", "# no frontmatter\n")     # invalid → rejected
    rc = promote.main([str(evolved), str(committed), "--rejected-dir", str(rejected)])
    assert rc == 0
    # the rejected SKILL.md must have been copied for inspection
    assert (rejected / "broken" / "SKILL.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_promote.py::test_rejected_candidates_are_copied_to_rejected_dir -v`
Expected: FAIL — `--rejected-dir` is an unrecognized argument.

- [ ] **Step 3: Write minimal implementation**

In `skillclaw_promote.py`, add the arg and copy logic. Add `import shutil` at top with the other imports, then modify `main`:

```python
    ap.add_argument("--rejected-dir", help="copy invalid candidates here for inspection")
    args = ap.parse_args(argv)
```

After the loop that fills `promote`/`dropped`, before the `json.dump`:

```python
    if args.rejected_dir:
        rej = Path(args.rejected_dir).expanduser()
        for d in dropped:
            dest = rej / d["name"]
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(d["path"], dest / "SKILL.md")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_promote.py -v`
Expected: PASS (existing 4 + 1 new)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_promote.py tests/python/test_skillclaw_promote.py
git commit -m "feat(skillclaw): promote copies rejected candidates to rejected/ for inspection"
```

---

## Task 10: Promote.sh — call new ingest+evolve, warn on rejected

**Files:**
- Modify: `configs/claude/scripts/skillclaw_promote.sh:62-104`
- Test: `tests/bats/skillclaw_promote.bats`

- [ ] **Step 1: Write the failing test**

Add to `tests/bats/skillclaw_promote.bats` (follow the existing stubbing pattern in that file — it sets `SKILLCLAW_*` env seams and a fake `git_ops.sh`):

```bash
@test "promote runs ingest+evolve scripts instead of the skillclaw binary" {
  run grep -E 'skillclaw_(ingest|evolve)\.py' "$REPO/configs/claude/scripts/skillclaw_promote.sh"
  [ "$status" -eq 0 ]
  run grep -c 'skillclaw evolve --mode workflow' "$REPO/configs/claude/scripts/skillclaw_promote.sh"
  [ "$output" -eq 0 ]
}

@test "promote warns when candidates are rejected" {
  run grep -Ei 'failed schema validation|rejected' "$REPO/configs/claude/scripts/skillclaw_promote.sh"
  [ "$status" -eq 0 ]
}
```

(Confirm the `$REPO` var name matches the file's existing setup; reuse whatever the other tests use to locate the repo root.)

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_promote.bats -f "ingest"`
Expected: FAIL — script still calls the `skillclaw` binary.

- [ ] **Step 3: Write minimal implementation**

In `skillclaw_promote.sh`, replace the scrub+evolve section (lines ~62–73) with:

```bash
INGEST="${SCRIPT_DIR}/skillclaw_ingest.py"
EVOLVE="${SCRIPT_DIR}/skillclaw_evolve.py"
TEMPLATE="${SKILLCLAW_TEMPLATE:-${SCRIPT_DIR}/../prompts/skillclaw_evolve.md}"
TRANSCRIPTS="${SKILLCLAW_TRANSCRIPTS:-$HOME/.claude/projects}"
STATE="${SKILLCLAW_STATE:-$HOME/.skillclaw/.ingest-state.json}"
REJECTED="${SKILLCLAW_REJECTED:-$HOME/.skillclaw/skills/rejected}"

# 1. Ingest transcripts → sessions (passive; no proxy).
if [[ "$DO_EVOLVE" == true ]]; then
    python3 "$INGEST" "$TRANSCRIPTS" "$SESSIONS" --state "$STATE" >/dev/null 2>&1 \
        || err "ingest returned non-zero (continuing)"
fi

# 2. Scrub captured sessions (best-effort; never blocks).
if [[ -d "$SESSIONS" ]]; then
    python3 "${SCRIPT_DIR}/skillclaw_scrub.py" "$SESSIONS" >/dev/null 2>&1 || true
fi

# 3. Evolve (skip with --no-evolve).
if [[ "$DO_EVOLVE" == true ]]; then
    python3 "$EVOLVE" "$SESSIONS" "$EVOLVED" --template "$TEMPLATE" \
        || err "evolve returned non-zero (continuing)"
fi
```

Then update the classify call to pass `--rejected-dir "$REJECTED"`, and after printing the diff table, add the warning:

```bash
classify_args=("$EVOLVED" "$COMMITTED" --rejected-dir "$REJECTED")
[[ -n "$SKILL" ]] && classify_args+=(--skill "$SKILL")
classify_json="$(python3 "${SCRIPT_DIR}/skillclaw_promote.py" "${classify_args[@]}")"

dropped_count="$(echo "$classify_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["dropped"]))')"
if [[ "$dropped_count" -gt 0 ]]; then
    err "Generated candidate(s), but ${dropped_count} failed schema validation. See ${REJECTED}"
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_promote.bats`
Expected: PASS (existing + 2 new). Then `pytest tests/python/test_skillclaw_promote.py -v` still PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_promote.sh tests/bats/skillclaw_promote.bats
git commit -m "feat(skillclaw): promote.sh drives ingest+evolve, warns on rejected candidates"
```

---

## Task 11: Config rewrite — drop proxy/capture, add ingest/evolve knobs

**Files:**
- Modify: `configs/claude/config/skillclaw.yml`
- Test: `tests/bats/skillclaw_config.bats`

- [ ] **Step 1: Write the failing test**

Replace proxy/capture assertions in `tests/bats/skillclaw_config.bats` with:

```bash
@test "skillclaw.yml has no proxy or capture blocks" {
  run python3 -c "import yaml; d=yaml.safe_load(open('$REPO/configs/claude/config/skillclaw.yml')); assert 'proxy' not in d and 'capture' not in d"
  [ "$status" -eq 0 ]
}

@test "skillclaw.yml defines ingest and claude-cli evolve engine" {
  run python3 -c "import yaml; d=yaml.safe_load(open('$REPO/configs/claude/config/skillclaw.yml')); assert d['ingest']['window_days']==30; assert d['evolve']['engine']=='claude-cli'; assert d['ingest']['settle_minutes']==5"
  [ "$status" -eq 0 ]
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_config.bats`
Expected: FAIL — current yml still has `proxy:`/`capture:` and lacks `ingest:`.

- [ ] **Step 3: Write the new config (content step)**

Replace `configs/claude/config/skillclaw.yml` entirely with:

```yaml
# SkillClaw runtime configuration (proxy-free, transcript-fed).
# Consumed by scripts/skillclaw_{ingest,evolve,promote}.{py,sh}.
# Deployed to ~/.claude/config/skillclaw.yml. NOTE: distinct from the vestigial
# upstream ~/.skillclaw/config.yaml — this file is the Manifest-owned source.

storage:
  root: ~/.skillclaw
  sessions: ~/.skillclaw/sessions
  evolved: ~/.skillclaw/skills
  rejected: ~/.skillclaw/skills/rejected
  state: ~/.skillclaw/.ingest-state.json

ingest:
  transcripts_dir: ~/.claude/projects
  window_days: 30              # all projects, recent window
  settle_minutes: 5           # skip files whose mtime is newer (still being written)
  max_tool_output_chars: 500  # truncate raw tool stdout/stderr beyond this; drop base64
  # allowlist: []             # optional future: restrict to project paths

evolve:
  engine: claude-cli          # `claude -p` headless, Max-backed
  token_budget: 100000        # map-reduce chunk threshold; stays clear of 200k limit
  prompt_template: ~/.claude/prompts/skillclaw_evolve.md

promotion:
  branch_prefix: skillclaw/evolve-
  pr_base: main
  pr_labels:
    - needs-review
    - follow-up
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_config.bats`
Expected: PASS. Also: `python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/skillclaw.yml'))"` exits 0.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/config/skillclaw.yml tests/bats/skillclaw_config.bats
git commit -m "feat(skillclaw): rewrite config — drop proxy/capture, add ingest/evolve knobs"
```

---

## Task 12: Bootstrap teardown — remove proxy stack, redefine enable/disable

**Files:**
- Modify: `bootstrap/lib/skillclaw.sh`
- Test: `tests/bats/skillclaw_lib.bats`

- [ ] **Step 1: Write the failing test**

In `tests/bats/skillclaw_lib.bats`, replace daemon/proxy/wrapper assertions with:

```bash
@test "skillclaw.sh no longer writes shell proxy wrappers" {
  run grep -Ec 'ANTHROPIC_BASE_URL|OPENAI_BASE_URL|_skillclaw_run|skillclaw_daemon' "$REPO/bootstrap/lib/skillclaw.sh"
  [ "$output" -eq 0 ]
}

@test "disable still removes any legacy wrapper block (clean teardown)" {
  run grep -q 'skillclaw_remove_wrappers' "$REPO/bootstrap/lib/skillclaw.sh"
  [ "$status" -eq 0 ]
}

@test "apply_state enables transcript evolution without a daemon" {
  run grep -Eq 'no daemon|transcript' "$REPO/bootstrap/lib/skillclaw.sh"
  [ "$status" -eq 0 ]
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/skillclaw_lib.bats`
Expected: FAIL — proxy/daemon symbols still present.

- [ ] **Step 3: Write minimal implementation**

Rewrite `bootstrap/lib/skillclaw.sh` to drop `install_skillclaw` (pip), `configure_skillclaw` (proxy setup), `skillclaw_daemon`, `skillclaw_supervisor_unit`, `skillclaw_install_supervisor`, and the base-URL lines in `skillclaw_write_wrappers`. **Keep** `skillclaw_remove_wrappers` (for clean teardown of any pre-existing wrapper block + launchd unit) and rewrite `skillclaw_apply_state`:

```bash
# Apply desired state. Transcript-fed evolution needs NO daemon and NO proxy —
# enabling just ensures storage exists and any legacy proxy wrappers are removed.
skillclaw_apply_state() {
    local profile="${SHELL_PROFILE_FILE:-$HOME/.zshrc}"
    # Always strip any legacy proxy wrapper block (full teardown of the old model).
    skillclaw_remove_wrappers "$profile"
    _skillclaw_remove_launchd
    if [[ "${ENABLE_SKILLCLAW:-false}" == true ]]; then
        mkdir -p "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
        chmod 700 "$SKILLCLAW_HOME" 2>/dev/null || true
        print_success "SkillClaw enabled (transcript evolution; no daemon, no proxy)"
    else
        print_info "SkillClaw disabled (storage left intact; nothing running)"
    fi
}

# Remove the retired launchd/systemd supervisor if a prior install left one.
_skillclaw_remove_launchd() {
    case "$(uname -s)" in
        Darwin)
            local plist="$HOME/Library/LaunchAgents/com.manifest.skillclaw.plist"
            [[ -f "$plist" ]] && { launchctl unload "$plist" >/dev/null 2>&1 || true; rm -f "$plist"; }
            ;;
        Linux)
            local unit="$HOME/.config/systemd/user/skillclaw.service"
            [[ -f "$unit" ]] && { systemctl --user disable --now skillclaw.service >/dev/null 2>&1 || true; rm -f "$unit"; }
            ;;
    esac
}
```

Keep `skillclaw_remove_wrappers` as-is (it deletes the marker block). Drop the now-unused `skillclaw_write_wrappers`, daemon, and supervisor functions.

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/skillclaw_lib.bats`
Expected: PASS. Then run the full bats suite for regressions: `bats tests/bats/`.

- [ ] **Step 5: Commit**

```bash
git add bootstrap/lib/skillclaw.sh tests/bats/skillclaw_lib.bats
git commit -m "feat(skillclaw): retire proxy/daemon/supervisor; enable = storage-only, full teardown"
```

---

## Task 13: Docs + full-suite green + lint

**Files:**
- Modify: `docs/SKILLCLAW.md`

- [ ] **Step 1: Rewrite `docs/SKILLCLAW.md`** to describe the proxy-free model: passive transcript ingestion, `claude -p` evolve engine, the ingest→scrub→evolve→classify→PR flow, the `~/.skillclaw/` annexation (Manifest-owned; upstream `config.yaml`/`dashboard.db` vestigial), and the `window_days`/`settle_minutes`/`max_tool_output_chars`/`token_budget` knobs. Remove all proxy/daemon/`SKILLCLAW_BYPASS`/port references.

- [ ] **Step 2: Run the full test suite**

Run:
```bash
pytest tests/python/ -v
bats tests/bats/
shellcheck configs/claude/scripts/skillclaw_promote.sh bootstrap/lib/skillclaw.sh
yamllint configs/claude/config/skillclaw.yml
```
Expected: all green; shellcheck and yamllint clean.

- [ ] **Step 3: Markdownlint the docs**

Run: `markdownlint docs/SKILLCLAW.md docs/superpowers/specs/2026-06-08-skillclaw-proxy-free-evolve-design.md docs/superpowers/plans/2026-06-08-skillclaw-proxy-free-evolve.md` (or the repo's configured linter)
Expected: clean (fix MD013 line-length / list issues as the repo convention requires).

- [ ] **Step 4: Commit**

```bash
git add docs/SKILLCLAW.md
git commit -m "docs(skillclaw): rewrite for proxy-free transcript-fed evolution"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage:**
- Passive transcript ingestion → Tasks 1–5. ✓
- Aggressive stripping (tool output, base64, tool_use input) → Tasks 1–2. ✓
- Window + settle (concurrency) → Tasks 4–5. ✓
- Incremental state → Task 5. ✓
- `claude -p` evolve engine + map-reduce chunking → Tasks 6–8. ✓
- Rejected candidates surfaced (not silent) → Tasks 9–10. ✓
- Reuse scrub + classify + PR-gating → Tasks 9–10 (scrub unchanged; promote.sh swaps evolve call). ✓
- Config rewrite (drop proxy/capture; ingest/evolve knobs) → Task 11. ✓
- Remove proxy/daemon/wrappers/supervisor; redefine enable → Task 12. ✓
- Annexation documented → Tasks 11–13. ✓
- Tests: ingest, evolve, promote-rejected, bats config/lib/promote → Tasks 1–13. ✓

**Type/name consistency:** Module API contract (top of plan) is used verbatim across tasks — `normalize_content`, `parse_transcript`, `within_window`, `is_settled`, `ingest`, `estimate_tokens`, `build_prompt`, `chunk_sessions`, `parse_candidates`, `write_candidates`, `evolve`, `subprocess_runner`. Env seams in promote.sh (`SKILLCLAW_TRANSCRIPTS`, `SKILLCLAW_STATE`, `SKILLCLAW_REJECTED`, `SKILLCLAW_TEMPLATE`) are new and self-consistent.

**Note for executor:** Task 9's test uses a `--rejected-dir` round-trip; verify the existing `skillclaw_promote.py` `main` arg-parsing block matches the line range cited before editing (the file may have shifted). Always re-read the target file region before applying an edit.
