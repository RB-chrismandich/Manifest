#!/usr/bin/env python3
"""
Pytest tests for plugins/manifest-delegate/scripts/session_hook.py (F2 fix).

Covers: SessionEnd reaping real dispatcher-created JobStore records (no more
dead ~/.manifest/delegate/jobs.json or inverted pgid-alive logic), SessionStart
session-capture persistence (0600), and delegate.py's transfer-source fallback
reading that same capture file when --source/env are both absent.

Run with: uv run --project configs/claude pytest tests/python/test_session_hook.py -q
"""

import importlib.util
import os
import stat
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "plugins" / "manifest-delegate" / "scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


delegate = _load("delegate", SCRIPTS_DIR / "delegate.py")
session_hook = _load("session_hook", SCRIPTS_DIR / "session_hook.py")


@pytest.fixture(autouse=True)
def _isolated_sessions_file(tmp_path, monkeypatch):
    """Redirect both modules' sessions.json to a per-test tmp path."""
    sessions_file = tmp_path / "sessions.json"
    monkeypatch.setattr(delegate.transfer, "SESSIONS_CAPTURE_FILE", str(sessions_file))
    monkeypatch.setattr(
        session_hook.delegate.transfer, "SESSIONS_CAPTURE_FILE", str(sessions_file)
    )
    return sessions_file


class TestSessionEndReap:
    def test_session_end_reaps_dead_job_in_workspace(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        cwd = str(tmp_path)
        store = delegate.JobStore(cwd=cwd)
        record = store.create("codex")
        job_id = record["job_id"]

        def _mark_running_dead(rec):
            rec["state"] = "running"
            rec["worker_pid"] = 999999999  # not a live pid
            rec["pgid"] = None
            # Age it past the worker-startup grace so the reaper treats a missing
            # worker as death rather than "still starting".
            rec["created_at"] = time.time() - delegate.WORKER_STARTUP_GRACE_SECONDS - 1
            return rec

        store.mutate(job_id, _mark_running_dead)

        rc = session_hook.handle_session_end({"cwd": cwd})
        assert rc == 0

        after = store.read(job_id)
        assert after["state"] == "failed"

    def test_session_end_startup_grace_does_not_fail_a_young_job(
        self, tmp_path, monkeypatch
    ):
        """L3: a freshly-created job whose worker has not yet acquired its lock
        (no live worker, age < startup grace) must NOT be reaped as failed."""
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        cwd = str(tmp_path)
        store = delegate.JobStore(cwd=cwd)
        job_id = store.create("codex")["job_id"]
        # Running, no live worker, but just created (within the grace window).
        store.mutate(
            job_id,
            lambda rec: dict(rec, state="running", worker_pid=999999999, pgid=None),
        )

        assert session_hook.handle_session_end({"cwd": cwd}) == 0
        assert store.read(job_id)["state"] == "running"

    def test_session_end_does_not_touch_live_job(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        cwd = str(tmp_path)
        store = delegate.JobStore(cwd=cwd)
        record = store.create("codex")
        job_id = record["job_id"]

        def _mark_running_alive(rec):
            rec["state"] = "running"
            rec["worker_pid"] = os.getpid()  # this test process: alive
            return rec

        store.mutate(job_id, _mark_running_alive)

        # Liveness is now proven by the worker.lock flock (pid-reuse-proof), not
        # os.kill(pid, 0). Hold that lock for the duration of the check so the
        # reaper sees the worker as genuinely alive and leaves the job untouched.
        import fcntl

        lock_path = os.path.join(store.job_dir(job_id), delegate.WORKER_LOCK_FILENAME)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            rc = session_hook.handle_session_end({"cwd": cwd})
            assert rc == 0
            after = store.read(job_id)
            assert after["state"] == "running"
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def test_session_end_noop_on_empty_workspace(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        # No jobs created at all — must not raise.
        rc = session_hook.handle_session_end({"cwd": str(tmp_path)})
        assert rc == 0


class TestSessionStartCapture:
    def test_session_start_writes_0600_sessions_file(self, tmp_path):
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "sess-1",
            "transcript_path": str(tmp_path / "transcript.jsonl"),
            "cwd": str(tmp_path),
        }
        rc = session_hook.handle_session_start(payload)
        assert rc == 0

        sessions_file = Path(session_hook.delegate.transfer.SESSIONS_CAPTURE_FILE)
        assert sessions_file.exists()
        mode = stat.S_IMODE(os.stat(sessions_file).st_mode)
        assert mode == 0o600

        data = session_hook._load_sessions()
        assert data["sess-1"]["cwd"] == str(tmp_path)
        assert data["sess-1"]["transcript_path"] == str(tmp_path / "transcript.jsonl")

    def test_session_start_missing_session_id_is_noop(self, tmp_path):
        rc = session_hook.handle_session_start({"hook_event_name": "SessionStart"})
        assert rc == 0
        assert not Path(session_hook.delegate.transfer.SESSIONS_CAPTURE_FILE).exists()

    def test_concurrent_session_starts_all_survive(self, tmp_path, monkeypatch):
        """L2: parallel harness sessions each call SessionStart concurrently; the
        inter-process flock must serialize the read-modify-write so no entry is
        lost. Threads each open their own fd → flock conflicts still serialize
        them, exercising the lock. Without it, the unlocked RMW would clobber."""
        import threading

        sessions_file = tmp_path / "sessions.json"
        monkeypatch.setattr(
            session_hook.delegate.transfer, "SESSIONS_CAPTURE_FILE", str(sessions_file)
        )
        n = 25
        barrier = threading.Barrier(n)

        def _start(i):
            barrier.wait()  # maximize contention
            session_hook.handle_session_start(
                {
                    "session_id": f"s{i:02d}",
                    "transcript_path": f"/t/{i}",
                    "cwd": f"/w/{i}",
                }
            )

        threads = [threading.Thread(target=_start, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        import json as _json

        saved = _json.loads(sessions_file.read_text())
        assert len(saved) == n, f"lost session entries: {len(saved)} of {n} survived"
        assert {f"s{i:02d}" for i in range(n)} == set(saved)


class TestTransferSourceFallback:
    def test_transfer_falls_back_to_captured_session_by_cwd(
        self, tmp_path, monkeypatch
    ):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("{}\n")
        session_hook.handle_session_start(
            {
                "hook_event_name": "SessionStart",
                "session_id": "sess-cwd",
                "transcript_path": str(transcript),
                "cwd": str(tmp_path),
            }
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)

        found = delegate._session_captured_transcript(str(tmp_path))
        assert found == str(transcript)

    def test_transfer_fails_closed_when_no_cwd_match(self, tmp_path):
        """G3: a workspace with no captured-session match must never leak the
        most recent transcript from an unrelated workspace (fail closed)."""
        older = tmp_path / "older.jsonl"
        newer = tmp_path / "newer.jsonl"
        older.write_text("{}\n")
        newer.write_text("{}\n")
        session_hook.handle_session_start(
            {
                "hook_event_name": "SessionStart",
                "session_id": "sess-old",
                "transcript_path": str(older),
                "cwd": "/some/other/dir",
            }
        )
        session_hook.handle_session_start(
            {
                "hook_event_name": "SessionStart",
                "session_id": "sess-new",
                "transcript_path": str(newer),
                "cwd": "/another/dir",
            }
        )

        found = delegate._session_captured_transcript("/no/match/here")
        assert found is None

    def test_transfer_returns_none_when_no_sessions_captured(self, tmp_path):
        assert delegate._session_captured_transcript(str(tmp_path)) is None

    def test_resolve_transfer_source_fails_closed_without_explicit_source(
        self, tmp_path, monkeypatch
    ):
        """Codex HIGH (rounds 2-3): even a sole cwd-matching capture (and any
        ambient env var) must NOT be auto-imported — neither channel is bound to
        the invoking session, so in a shared worktree either could be another
        session's transcript. With no --source, transfer fails closed regardless
        of what the workspace capture or environment holds."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("{}\n")
        session_hook.handle_session_start(
            {
                "hook_event_name": "SessionStart",
                "session_id": "sess-x",
                "transcript_path": str(transcript),
                "cwd": str(tmp_path),
            }
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(delegate.TRANSCRIPT_PATH_ENV, str(transcript))

        class _Args:
            source = None

        real_source, error = delegate._resolve_transfer_source(_Args())
        assert real_source is None, "no auto-inference: --source must be explicit"
        assert error is not None and "--source" in error


class TestTransferSessionDisambiguation:
    """Two sessions sharing one worktree must never import each other's
    transcript. `transfer` has no way to identify which session invoked it, so
    an ambiguous capture set is refused rather than guessed at."""

    def _capture(self, session_id, transcript, cwd):
        session_hook.handle_session_start(
            {
                "hook_event_name": "SessionStart",
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(cwd),
            }
        )

    def test_two_sessions_same_cwd_refuses_instead_of_guessing(
        self, tmp_path, monkeypatch
    ):
        """The bug: the fallback took the last cwd-matching entry, so whichever
        session ran `transfer` could receive the OTHER session's transcript. The
        fix requires --source unconditionally, so two shared-worktree sessions
        can never resolve a source implicitly at all."""
        mine = tmp_path / "mine.jsonl"
        theirs = tmp_path / "theirs.jsonl"
        mine.write_text("{}\n")
        theirs.write_text("{}\n")
        self._capture("sess-mine", mine, tmp_path)
        self._capture("sess-theirs", theirs, tmp_path)

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)

        class _Args:
            source = None

        real_source, error = delegate._resolve_transfer_source(_Args())
        assert real_source is None, "two shared-worktree sessions must not resolve a source"
        assert error is not None and "--source" in error

    def test_explicit_source_selects_the_right_transcript(self, tmp_path, monkeypatch):
        mine = tmp_path / "mine.jsonl"
        theirs = tmp_path / "theirs.jsonl"
        mine.write_text("{}\n")
        theirs.write_text("{}\n")
        self._capture("sess-mine", mine, tmp_path)
        self._capture("sess-theirs", theirs, tmp_path)

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)
        monkeypatch.setattr(delegate.transfer, "TRANSCRIPT_ROOTS", (str(tmp_path),))

        class _Args:
            source = str(mine)

        real_source, error = delegate._resolve_transfer_source(_Args())
        assert error is None
        assert os.path.realpath(real_source) == os.path.realpath(str(mine))

    def test_ambiguous_capture_yields_no_transcript(self, tmp_path):
        """The lower-level lookup fails closed on ambiguity too, so no other
        caller can reintroduce the guess."""
        a = tmp_path / "a.jsonl"
        b = tmp_path / "b.jsonl"
        a.write_text("{}\n")
        b.write_text("{}\n")
        self._capture("sess-a", a, tmp_path)
        self._capture("sess-b", b, tmp_path)

        assert delegate._session_captured_transcript(str(tmp_path)) is None
        assert len(delegate._captured_sessions_for_cwd(str(tmp_path))) == 2

    def test_session_end_evicts_entry_restoring_unambiguous_transfer(
        self, tmp_path, monkeypatch
    ):
        """SessionEnd removing the finished session's entry is what returns the
        remaining live session to a working no---source transfer."""
        mine = tmp_path / "mine.jsonl"
        theirs = tmp_path / "theirs.jsonl"
        mine.write_text("{}\n")
        theirs.write_text("{}\n")
        self._capture("sess-mine", mine, tmp_path)
        self._capture("sess-theirs", theirs, tmp_path)

        rc = session_hook.handle_session_end(
            {
                "hook_event_name": "SessionEnd",
                "session_id": "sess-theirs",
                "cwd": str(tmp_path),
            }
        )
        assert rc == 0
        assert "sess-theirs" not in session_hook._load_sessions()
        assert delegate._session_captured_transcript(str(tmp_path)) == str(mine)

    def test_session_end_eviction_is_idempotent(self, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        self._capture("sess-1", transcript, tmp_path)
        payload = {
            "hook_event_name": "SessionEnd",
            "session_id": "sess-1",
            "cwd": str(tmp_path),
        }
        assert session_hook.handle_session_end(payload) == 0
        assert session_hook.handle_session_end(payload) == 0
        assert session_hook._load_sessions() == {}

    def test_capture_entry_is_timestamped(self, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        before = time.time()
        self._capture("sess-1", transcript, tmp_path)
        entry = session_hook._load_sessions()["sess-1"]
        assert before <= entry["captured_at"] <= time.time()
