#!/usr/bin/env python3
"""Standalone review: diff assembly and the `review` command.

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_review.py -q
"""

import json

from _delegate_inproc import _valid_backend, delegate

# ---------------------------------------------------------------------------
# review subcommand (T026, Phase 6 baseline parity)
# ---------------------------------------------------------------------------


class _ReviewArgs:
    backend = None
    background = False
    wait = True
    model = None
    budget = None
    adversarial = None
    base = None
    scope = "auto"
    json = True


def _init_git_repo(tmp_path):
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n")
    sp.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("two\n")


class TestReviewDiffAssembly:
    def test_working_tree_scope_captures_uncommitted_change(self, tmp_path):
        _init_git_repo(tmp_path)
        diff = delegate.assemble_review_diff("working-tree", None, cwd=str(tmp_path))
        assert "-one" in diff
        assert "+two" in diff

    def test_branch_scope_uses_base_ref(self, tmp_path):
        import subprocess as sp

        _init_git_repo(tmp_path)
        sp.run(["git", "commit", "-q", "-am", "second"], cwd=tmp_path, check=True)
        diff = delegate.assemble_review_diff("branch", "HEAD~1", cwd=str(tmp_path))
        assert "-one" in diff
        assert "+two" in diff

    def test_auto_scope_falls_back_to_working_tree(self, tmp_path):
        _init_git_repo(tmp_path)
        diff = delegate.assemble_review_diff("auto", None, cwd=str(tmp_path))
        assert "+two" in diff

    def test_untracked_dash_prefixed_filename_is_not_injected_as_option(self, tmp_path):
        """G2: an untracked file named like a git option must not be parsed as one."""
        _init_git_repo(tmp_path)
        evil_name = "--output=pwned"
        (tmp_path / evil_name).write_text("payload\n")
        config_before = (tmp_path / ".git" / "config").read_text()

        diff = delegate._untracked_diff(str(tmp_path))

        config_after = (tmp_path / ".git" / "config").read_text()
        assert config_after == config_before
        assert evil_name in diff
        assert "payload" in diff


class TestReviewCommand:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(
            delegate.review,
            "assemble_review_diff",
            lambda scope, base, cwd=None: "diff --git a b\n",
        )

    def test_review_forces_read_only_args(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["record"] = record
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 0
        assert captured["record"]["kind"] == "review"
        assert captured["record"].get("write") is False
        assert "diff --git a b" in captured["prompt"]

    def test_adversarial_switches_prompt_with_focus(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        args.adversarial = ["auth", "boundary"]
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 0
        assert "adversarial" in captured["prompt"].lower()
        assert "auth boundary" in captured["prompt"] or "auth" in captured["prompt"]

    def test_findings_presented_severity_first_in_envelope(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {
                    "outcome": "success",
                    "findings": [
                        {"severity": "low", "text": "nit"},
                        {"severity": "high", "text": "sql injection"},
                    ],
                },
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        severities = [f["severity"] for f in out["findings"]]
        assert severities.index("high") < severities.index("low")

    def test_background_reuses_job_records(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        args = _ReviewArgs()
        args.backend = "codex"
        args.background = True
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert "job_id" in out
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.read(out["job_id"])
        assert record["kind"] == "review"
