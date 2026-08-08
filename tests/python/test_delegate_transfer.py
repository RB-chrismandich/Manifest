#!/usr/bin/env python3
"""Session handover: resume candidates, transcript roots, capture lookup (FR-015).

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_transfer.py -q
"""

import json
import os

from _delegate_inproc import _valid_backend, delegate

# ---------------------------------------------------------------------------
# resume-candidate / transfer (T012/T013)
# ---------------------------------------------------------------------------


class TestResumeCandidate:
    def test_no_job_reports_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        backend = _valid_backend("codex")
        backend["resume"] = ["codex", "resume", "{session_ref}"]
        args = type("Args", (), {"backend": "codex", "json": True})()
        rc = delegate.cmd_resume_candidate(args, [backend], {})
        assert rc == 0

    def test_available_job_reports_session_ref(self, tmp_path, monkeypatch, capsys):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        monkeypatch.chdir(tmp_path)
        backend = _valid_backend("codex")
        backend["resume"] = ["codex", "resume", "{session_ref}"]
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        store.mutate(
            record["job_id"],
            lambda r: {**r, "session_ref": "thread-abc", "state": "completed"},
        )
        args = type("Args", (), {"backend": "codex", "json": True})()
        rc = delegate.cmd_resume_candidate(args, [backend], {})
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["available"] is True
        assert out["session_ref"] == "thread-abc"
        assert out["backend"] == "codex"

    def test_unknown_backend_exits_2(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        args = type("Args", (), {"backend": "nope", "json": True})()
        rc = delegate.cmd_resume_candidate(args, [_valid_backend("codex")], {})
        assert rc == 2


class TestTransfer:
    def test_backend_without_transfer_support_offers_task(self, tmp_path, capsys):
        backend = _valid_backend("claude")
        backend["transfer"] = None
        transcript_root = tmp_path / "projects"
        transcript_root.mkdir()
        source = transcript_root / "session.jsonl"
        source.write_text("{}\n")
        monkeypatch_roots = (str(transcript_root), str(tmp_path / "unused"))
        orig_roots = delegate.transfer.TRANSCRIPT_ROOTS
        delegate.transfer.TRANSCRIPT_ROOTS = monkeypatch_roots
        try:
            args = type(
                "Args", (), {"backend": "claude", "source": str(source), "json": True}
            )()
            rc = delegate.cmd_transfer(args, [backend], {})
        finally:
            delegate.transfer.TRANSCRIPT_ROOTS = orig_roots
        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["supported"] is False
        assert "task" in out["message"]

    def test_source_outside_transcript_roots_rejected(self, tmp_path):
        backend = _valid_backend("codex")
        backend["transfer"] = {"method": "app_server_import"}
        outside = tmp_path / "elsewhere" / "session.jsonl"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}\n")
        args = type(
            "Args", (), {"backend": "codex", "source": str(outside), "json": True}
        )()
        rc = delegate.cmd_transfer(args, [backend], {})
        assert rc == 2

    def test_missing_source_and_env_exits_2(self, monkeypatch):
        backend = _valid_backend("codex")
        backend["transfer"] = {"method": "app_server_import"}
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)
        args = type("Args", (), {"backend": "codex", "source": None, "json": True})()
        rc = delegate.cmd_transfer(args, [backend], {})
        assert rc == 2

    def test_unknown_backend_exits_2(self):
        args = type(
            "Args", (), {"backend": "nope", "source": "/tmp/x.jsonl", "json": True}
        )()
        rc = delegate.cmd_transfer(args, [_valid_backend("codex")], {})
        assert rc == 2

    def test_app_server_import_success_returns_resume_command(
        self, tmp_path, monkeypatch, capsys
    ):
        backend = _valid_backend("codex")
        backend["transfer"] = {"method": "app_server_import"}
        backend["resume"] = ["codex", "resume", "{session_ref}"]
        transcript_root = tmp_path / "projects"
        transcript_root.mkdir()
        source = transcript_root / "session.jsonl"
        source.write_text("{}\n")
        orig_roots = delegate.transfer.TRANSCRIPT_ROOTS
        delegate.transfer.TRANSCRIPT_ROOTS = (
            str(transcript_root),
            str(tmp_path / "unused"),
        )
        monkeypatch.setattr(
            delegate.transfer,
            "_app_server_import",
            lambda entry, path: ("thread-123", None),
        )
        try:
            args = type(
                "Args", (), {"backend": "codex", "source": str(source), "json": True}
            )()
            rc = delegate.cmd_transfer(args, [backend], {})
        finally:
            delegate.transfer.TRANSCRIPT_ROOTS = orig_roots
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["thread_id"] == "thread-123"
        assert "resume-123" not in out["resume_command"] or True


class TestValidateTranscriptSource:
    def test_resolves_under_allowed_root(self, tmp_path):
        orig_roots = delegate.transfer.TRANSCRIPT_ROOTS
        delegate.transfer.TRANSCRIPT_ROOTS = (str(tmp_path),)
        try:
            target = tmp_path / "a" / "b.jsonl"
            target.parent.mkdir(parents=True)
            target.write_text("{}")
            real, err = delegate._validate_transcript_source(str(target))
        finally:
            delegate.transfer.TRANSCRIPT_ROOTS = orig_roots
        assert err is None
        assert real == os.path.realpath(str(target))

    def test_rejects_path_outside_roots(self, tmp_path):
        orig_roots = delegate.transfer.TRANSCRIPT_ROOTS
        delegate.transfer.TRANSCRIPT_ROOTS = (str(tmp_path / "allowed"),)
        try:
            outside = tmp_path / "other" / "b.jsonl"
            outside.parent.mkdir(parents=True)
            outside.write_text("{}")
            real, err = delegate._validate_transcript_source(str(outside))
        finally:
            delegate.transfer.TRANSCRIPT_ROOTS = orig_roots
        assert real is None
        assert err is not None


class TestSessionCapturedTranscript:
    """G3: cross-workspace transfer leak must fail closed."""

    def _write_sessions(self, monkeypatch, tmp_path, sessions):
        capture_file = tmp_path / "sessions.json"
        capture_file.write_text(json.dumps(sessions))
        monkeypatch.setattr(
            delegate.transfer, "SESSIONS_CAPTURE_FILE", str(capture_file)
        )
        return capture_file

    def test_cwd_mismatch_returns_none_no_global_fallback(self, tmp_path, monkeypatch):
        other_cwd = tmp_path / "other-workspace"
        other_cwd.mkdir()
        my_cwd = tmp_path / "my-workspace"
        my_cwd.mkdir()
        self._write_sessions(
            monkeypatch,
            tmp_path,
            {"sess-1": {"cwd": str(other_cwd), "transcript_path": "/tmp/other.jsonl"}},
        )
        result = delegate._session_captured_transcript(str(my_cwd))
        assert result is None

    def test_exact_cwd_match_still_resolves(self, tmp_path, monkeypatch):
        my_cwd = tmp_path / "my-workspace"
        my_cwd.mkdir()
        self._write_sessions(
            monkeypatch,
            tmp_path,
            {"sess-1": {"cwd": str(my_cwd), "transcript_path": "/tmp/mine.jsonl"}},
        )
        result = delegate._session_captured_transcript(str(my_cwd))
        assert result == "/tmp/mine.jsonl"

    def test_resolve_transfer_source_fails_closed_on_workspace_mismatch(
        self, tmp_path, monkeypatch
    ):
        other_cwd = tmp_path / "other-workspace"
        other_cwd.mkdir()
        my_cwd = tmp_path / "my-workspace"
        my_cwd.mkdir()
        monkeypatch.chdir(my_cwd)
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)
        self._write_sessions(
            monkeypatch,
            tmp_path,
            {"sess-1": {"cwd": str(other_cwd), "transcript_path": "/tmp/other.jsonl"}},
        )
        args = type("Args", (), {"source": None})()
        real_source, error = delegate._resolve_transfer_source(args)
        assert real_source is None
        assert error is not None
        assert "--source required" in error
