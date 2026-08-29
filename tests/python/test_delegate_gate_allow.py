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


def _forbid_jobstore_initialization(message):
    def fail():
        raise AssertionError(message)

    return fail


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

    def test_disabled_gate_does_not_initialize_jobstore(self, tmp_path, monkeypatch):
        """A disabled gate must allow without touching durable job state."""
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.gate.jobstore,
            "JobStore",
            _forbid_jobstore_initialization("disabled gate initialized JobStore"),
        )
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0

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
        assert payload == {"decision": "approve", "reason": "gate disabled"}

    def test_no_edits_in_finishing_turn_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.gate.jobstore,
            "JobStore",
            _forbid_jobstore_initialization("no-edit gate initialized JobStore"),
        )
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

    def test_stop_hook_active_does_not_initialize_jobstore(
        self, tmp_path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.gate.jobstore,
            "JobStore",
            _forbid_jobstore_initialization(
                "stop-hook re-entry initialized JobStore"
            ),
        )
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "x"}}]
        )
        args.stop_hook_active = True
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": True}}, set()
        )
        assert rc == 0

    def test_enabled_gate_with_edits_initializes_jobstore_before_execution(
        self, tmp_path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        store = object()
        constructor_calls = []
        executed_with = []

        def construct_store():
            constructor_calls.append(True)
            return store

        def execute_gate(store_, *args):
            executed_with.append(store_)
            return 0

        monkeypatch.setattr(delegate.gate.jobstore, "JobStore", construct_store)
        monkeypatch.setattr(delegate.gate, "_gate_execute", execute_gate)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "fix it"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "name": "Edit", "input": {}}
                        ],
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
        assert constructor_calls == [True]
        assert executed_with == [store]

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
