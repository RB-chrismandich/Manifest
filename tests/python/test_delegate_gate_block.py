#!/usr/bin/env python3
"""Review-gate BLOCK decisions, fail-open behaviour, and budget handling.

Split out of the former test_delegate_dispatcher.py: TestGateCommand alone was
531 lines across 22 methods, past both the file and the class ceiling. The seam
is behavioural — this file covers blocking, every fail-open route, and the budget cap; the
sibling covers the allow paths.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_gate_block.py -q
"""

import json

from _delegate_inproc import _valid_backend, delegate


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


class TestGateBlocks:
    """A material finding must block exactly once, with a reason that tells the
    developer what to do and forbids the model from acting on it itself."""

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

    def test_block_reason_forbids_tools_and_ends_developer_decides(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {
                    "outcome": "success",
                    "findings": [
                        {"severity": "high", "text": "sql injection"},
                        {"severity": "low", "text": "nit"},
                    ],
                },
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
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
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        reason = out["reason"]
        assert (
            "no tool call" in reason.lower()
            or "do not make any tool call" in reason.lower()
        )
        assert "ask" in reason.lower()
        assert reason.strip().endswith("developer decides.")
        assert reason.index("high") < reason.index("low")

    def test_block_decision_emitted_exactly_once(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {
                    "outcome": "success",
                    "findings": [{"severity": "medium", "text": "issue"}],
                },
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Write", "input": {}}],
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
        out_text = capsys.readouterr().out.strip()
        assert out_text.count('"decision"') == 1


class TestGateFailsOpen:
    """The gate is advisory: an unready backend, a timeout, or an unparseable
    transcript must degrade to `allow` plus a systemMessage, never to a block."""

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

    def test_unready_backend_fails_open_with_system_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.backend, "_executable_missing", lambda argv: "not installed"
        )
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
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
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert "systemMessage" in out
        assert "review gate skipped" in out["systemMessage"]
        assert "review gate skipped" in captured.err

    def test_timeout_fails_open_with_system_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.worker,
            "_run_backend_and_finish",
            lambda *a, **k: {"state": "timeout"},
        )
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
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
        out = json.loads(capsys.readouterr().out)
        assert "systemMessage" in out

    def test_malformed_transcript_fails_open_with_system_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        bad_path = tmp_path / "missing.jsonl"
        args = _GateArgs()
        args.transcript = str(bad_path)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert "systemMessage" in out
        assert captured.err


class TestGateBudget:
    """The gate's review budget is clamped below the Stop-hook timeout and the
    clamped value is what the job record carries."""

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

    def test_budget_over_cap_is_clamped_to_840(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["budget"] = record.get("budget_seconds")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {
                "review_gate": {
                    "enabled": True,
                    "backend": "codex",
                    "budget_seconds": 5000,
                }
            },
            set(),
        )
        assert rc == 0
        assert delegate.GATE_BUDGET_CAP_SECONDS == 840

    def test_budget_seconds_persisted_to_running_record(self, tmp_path, monkeypatch):
        """G5: the gate's mutator must RETURN the updated record so mutate()
        persists it. Before the fix, a `rec.update(...)`-returning-None
        mutator caused mutate() to treat the mutation as refused, and the
        runner fell back to the 600s default instead of the configured
        budget."""
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["budget"] = record.get("budget_seconds")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {
                "review_gate": {
                    "enabled": True,
                    "backend": "codex",
                    "budget_seconds": 17,
                }
            },
            set(),
        )
        assert rc == 0
        assert captured.get("budget") == 17, (
            "expected configured budget_seconds=17 to reach the runner, got {!r} "
            "(600 = silent default fallback, 840 = cap constant)".format(
                captured.get("budget")
            )
        )


class TestGateEnvelopeParsing:
    """End-to-end through real envelope parsing: a material finding blocks, and
    malformed backend output never silently allows."""

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

    def _edit_transcript(self, tmp_path):
        return self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )

    def test_e2e_material_finding_blocks_through_real_envelope_parsing(
        self, tmp_path, monkeypatch, capsys
    ):
        """G4: a real fenced-JSON backend reply, parsed by the actual
        `normalize_envelope` (not a stubbed `_run_backend_and_finish`), must
        still produce a block decision when it reports a material finding."""
        self._setup(tmp_path, monkeypatch)
        raw_output = (
            "Reviewed the diff for defects.\n\n"
            "```json\n"
            "{\n"
            '  "backend": "codex",\n'
            '  "model": "gpt-5",\n'
            '  "outcome": "success",\n'
            '  "attempted": "reviewed diff",\n'
            '  "changes": [],\n'
            '  "succeeded": [],\n'
            '  "failed": [],\n'
            '  "follow_ups": [],\n'
            '  "findings": [{"severity": "high", "text": "sql injection in query builder"}]\n'
            "}\n"
            "```\n"
        )
        monkeypatch.setattr(
            delegate.process,
            "_spawn_backend",
            lambda entry, argv, prompt_bytes, job_dir, budget, on_pgid=None: (
                0,
                raw_output,
                None,
                False,
                None,
            ),
        )
        args = _GateArgs()
        args.transcript = self._edit_transcript(tmp_path)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        assert "sql injection" in out["reason"].lower()

    def test_e2e_malformed_backend_output_never_silently_allows(
        self, tmp_path, monkeypatch, capsys
    ):
        """G4: when the backend emits no usable fenced JSON, `normalize_envelope`
        produces a failure envelope with a non-empty `error`; the gate must
        surface that as an explicit systemMessage (fail-open, not silent)."""
        self._setup(tmp_path, monkeypatch)
        raw_output = "I looked at the diff but forgot to emit any JSON block, sorry.\n"
        monkeypatch.setattr(
            delegate.process,
            "_spawn_backend",
            lambda entry, argv, prompt_bytes, job_dir, budget, on_pgid=None: (
                0,
                raw_output,
                None,
                False,
                None,
            ),
        )
        args = _GateArgs()
        args.transcript = self._edit_transcript(tmp_path)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert '"decision": "block"' not in captured.out
        assert "systemMessage" in out
        assert "review gate skipped" in out["systemMessage"]
        assert "review gate skipped" in captured.err

    def test_gate_validate_findings_rejects_non_list_findings(self):
        """G4: `_gate_validate_findings` itself must reject a well-formed
        envelope (no `error`, valid `outcome`) whose `findings` is not a
        list, rather than crashing or treating it as empty/allow."""
        findings, error_reason = delegate._gate_validate_findings(
            {"outcome": "success", "findings": "oops"}
        )
        assert findings is None
        assert error_reason
        assert "malformed findings" in error_reason

    def test_gate_validate_findings_rejects_missing_findings_field(self):
        """Codex HIGH: an omitted `findings` field is an INCOMPLETE review, not
        "no findings". A schema-valid success envelope that simply omits findings
        must NOT reach the allow path — the gate returns an error reason so the
        Stop hook surfaces it, instead of defaulting to [] and allowing."""
        findings, error_reason = delegate._gate_validate_findings(
            {"outcome": "success"}
        )
        assert findings is None
        assert error_reason and "no findings field" in error_reason

    def test_gate_validate_findings_accepts_explicit_empty_list(self):
        """The one legitimate allow: findings is PRESENT and empty — the
        reviewer looked and found nothing."""
        findings, error_reason = delegate._gate_validate_findings(
            {"outcome": "success", "findings": []}
        )
        assert findings == []
        assert error_reason is None
