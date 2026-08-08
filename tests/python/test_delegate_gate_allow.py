#!/usr/bin/env python3
"""Review-gate ALLOW paths: when the gate declines to run at all.

Split out of the former test_delegate_dispatcher.py: TestGateCommand alone was
531 lines across 22 methods, past both the file and the class ceiling. The seam
is behavioural — this file covers every route to `allow`, the sibling covers blocking and
fail-open.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_gate_allow.py -q
"""

import json
from pathlib import Path

from _delegate_inproc import _valid_backend, delegate

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


class TestGateAllows:
    """Every path that reaches an `allow` decision without a backend review:
    the gate disabled, no edits in the finishing turn, or re-entry guarded by
    stop_hook_active."""

    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(
            delegate.review,
            "assemble_review_diff",
            lambda scope, base, cwd=None: "diff --git a b\n",
        )

    def _transcript(self, tmp_path, lines):
        path = tmp_path / "transcript.jsonl"
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        return str(path)

    def test_disabled_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0

    def test_disabled_gate_leaves_zero_active_jobs(self, tmp_path, monkeypatch):
        """G8: a gate that short-circuits on the disabled check must not
        create a queued job record. Before the fix, cmd_gate created the job
        record before the enabled check ran, leaking a permanent queued job
        every time the gate is skipped."""
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0
        store = delegate.JobStore(cwd=str(tmp_path))
        jobs = list(store.list()) if hasattr(store, "list") else []
        active = [j for j in jobs if j.get("state") in ("queued", "running")]
        assert active == [], (
            f"disabled gate must not leave any queued/running jobs: {active!r}"
        )

    def test_disabled_allows_prints_decision_json(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        args.json = True
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0
        out = capsys.readouterr().out.strip()
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload == {"decision": "allow", "reason": "gate disabled"}

    def test_no_edits_in_finishing_turn_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        entries = [
            {"type": "user", "message": {"role": "user", "content": "do a thing"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                },
            },
        ]
        args = _GateArgs()
        args.transcript = self._transcript(tmp_path, entries)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0

    def test_stop_hook_active_is_immediate_allow(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        entries = [
            {"type": "user", "message": {"role": "user", "content": "do a thing"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                },
            },
        ]
        args = _GateArgs()
        args.transcript = self._transcript(tmp_path, entries)
        args.stop_hook_active = True
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "decision" not in out

    def test_stop_hook_active_records_gate_job(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "x"}}]
        )
        args.stop_hook_active = True
        delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": True}}, set()
        )
        store = delegate.JobStore(cwd=str(tmp_path))
        jobs = list(store.list()) if hasattr(store, "list") else None
        if jobs is not None:
            assert any(j.get("kind") == "gate" for j in jobs)

    def test_bash_only_turn_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0

    def test_real_transcript_edit_fixture_detected(self):
        assert (
            delegate._finishing_turn_has_edits(
                str(FIXTURES_DIR / "real_transcript_edit.jsonl")
            )
            is True
        )

    def test_real_transcript_bash_only_fixture_not_detected(self):
        assert (
            delegate._finishing_turn_has_edits(
                str(FIXTURES_DIR / "real_transcript_bash_only.jsonl")
            )
            is False
        )
