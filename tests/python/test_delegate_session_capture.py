"""Codex `jsonl_event` session capture against REAL captured CLI output (T009).

The other session-capture coverage (test_delegate_resume.py) exercises the
`output_scan` method through synthetic stub output. This file pins the
`jsonl_event` method to fixtures captured from a real `codex exec --json` run,
so a change in the codex event stream — or in the registry's declared event or
field name — fails here rather than silently returning a null session ref.

Provenance of the fixtures: tests/python/fixtures/codex/README.md.

Run with: uv run --project configs/claude pytest \
    tests/python/test_delegate_session_capture.py -q
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "manifest-delegate"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "codex"

sys.path.insert(0, str(PLUGIN_ROOT))

from manifest_delegate.backend import extract_session_ref

CAPTURED_THREAD_ID = "01a0097c-cb56-7f91-a29f-7c7906fb664a"


def _codex_entry():
    """The shipped codex registry entry — not a hand-written stand-in."""
    registry = json.loads((PLUGIN_ROOT / "config" / "backends.json").read_text())
    for entry in registry["backends"]:
        if entry["id"] == "codex":
            return entry
    raise AssertionError("codex entry missing from backends.json")


class TestCodexJsonlEventCapture:
    def test_registry_declares_the_event_the_real_cli_emits(self):
        cap = _codex_entry()["session_id_capture"]
        first = json.loads(
            (FIXTURES / "exec_thread_started.jsonl").read_text().splitlines()[0]
        )
        assert cap["method"] == "jsonl_event"
        assert cap["event"] == first["type"]
        assert cap["field"] in first

    def test_thread_started_yields_session_ref(self):
        raw = (FIXTURES / "exec_thread_started.jsonl").read_text()
        assert extract_session_ref(_codex_entry(), raw) == CAPTURED_THREAD_ID

    def test_older_cli_without_thread_started_yields_none(self):
        """Resume is unavailable, not an error (FR-015 disclosure path)."""
        raw = (FIXTURES / "exec_no_thread_started.jsonl").read_text()
        assert extract_session_ref(_codex_entry(), raw) is None

    def test_non_json_noise_lines_are_skipped_not_fatal(self):
        """Real codex runs interleave stderr warnings into captured output."""
        lines = (FIXTURES / "exec_thread_started.jsonl").read_text().splitlines()
        noisy = "\n".join(["ERROR codex_models_manager: refresh failed", *lines])
        assert extract_session_ref(_codex_entry(), noisy) == CAPTURED_THREAD_ID

    def test_empty_output_yields_none(self):
        assert extract_session_ref(_codex_entry(), "") is None
