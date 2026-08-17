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
            return {
                "state": "completed",
                "envelope": {"outcome": "success", "findings": []},
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 0
        assert captured["record"]["kind"] == "review"
        assert captured["record"].get("write") is False
        assert "diff --git a b" in captured["prompt"]

    def test_oversize_review_diff_is_rejected_before_a_job_record_exists(
        self, tmp_path, monkeypatch
    ):
        """A diff over the dispatcher's 1 MiB task ceiling fails cleanly.

        `review` builds its prompt internally, so it never passes through the
        stdin/file readers that enforce TASK_LIMIT. Registry bounds alone let a
        1-10 MiB prompt through, and the ceiling was then hit deep in the worker
        as an unhandled ValueError: a traceback, exit 1, and a `queued` job
        record for a worker that never spawned. Found by running the shipped
        `review --adversarial --background` against this repository's own
        working tree, 2026-08-16.
        """
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.review,
            "assemble_review_diff",
            lambda scope, base, cwd=None: "x" * (1024 * 1024 + 1),
        )
        args = _ReviewArgs()
        args.backend = "codex"
        args.background = True
        args.wait = False
        # The shipped codex entry declares a 10 MiB transport bound, which is
        # LOOSER than the dispatcher's own 1 MiB ceiling. Mirror that here: a
        # fixture whose registry bound is already under TASK_LIMIT hides the
        # gap, because the registry check catches the prompt first.
        entry = _valid_backend("codex")
        entry["input"]["max_payload_bytes"] = 10 * 1024 * 1024

        rc = delegate.cmd_review(args, [entry], {}, set())

        assert rc == 2
        delegations = tmp_path / "delegations"
        records = list(delegations.rglob("record.json")) if delegations.exists() else []
        assert records == [], f"oversize review left orphan job records: {records}"

    def test_review_prompt_requires_parseable_result_envelope(
        self, tmp_path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {
                "state": "completed",
                "envelope": {"outcome": "success", "findings": []},
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "antigravity"

        assert (
            delegate.cmd_review(args, [_valid_backend("antigravity")], {}, set()) == 0
        )
        assert (
            "End your final message with exactly one fenced JSON block"
            in captured["prompt"]
        )
        assert (
            "Do not create artifacts, plans, files, or ask for approval"
            in captured["prompt"]
        )
        assert '"findings"' in captured["prompt"]

    def test_review_omitting_findings_is_a_failure_not_a_clean_pass(
        self, tmp_path, monkeypatch, capsys
    ):
        """Codex HIGH: a non-failure review envelope that OMITS findings is an
        incomplete result — `review` must not exit 0 reporting no issues. Mirror
        the Stop gate: convert it to a failure (exit 1)."""
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 1, "omitted findings must not be a clean pass"

    def test_review_with_explicit_empty_findings_passes(self, tmp_path, monkeypatch):
        """The one legitimate pass: findings PRESENT and empty (reviewer looked,
        found nothing)."""
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {"outcome": "success", "findings": []},
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 0

    def test_review_partial_outcome_is_not_a_clean_pass(self, tmp_path, monkeypatch):
        """Codex HIGH (round 8): outcome=partial means the reviewer could not
        inspect the whole diff — even with empty findings it is NOT a clean
        review, so `review` must exit nonzero rather than report success."""
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {"outcome": "partial", "findings": []},
            }

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 1, "partial coverage must not be a clean exit 0"

    def test_adversarial_switches_prompt_with_focus(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {
                "state": "completed",
                "envelope": {"outcome": "success", "findings": []},
            }

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


class TestShippedAntigravityInvocation:
    def test_antigravity_passes_prompt_as_print_flag_value(self, tmp_path):
        from _delegate_inproc import REPO_ROOT

        cfg = json.loads(
            (REPO_ROOT / "plugins/manifest-delegate/config/backends.json").read_text()
        )
        entry = next(b for b in cfg["backends"] if b["id"] == "antigravity")
        prompt = "review this exact change"

        argv, process_prompt = delegate.worker._build_backend_invocation(
            entry,
            False,
            "gemini-3.6-flash-low",
            {"output_file": str(tmp_path / "output.txt")},
            prompt.encode("utf-8"),
        )

        assert argv[:3] == ["agy", "--print", prompt]
        assert (entry.get("input") or {}).get("transport") == "argv"
        assert process_prompt == prompt.encode("utf-8")


class TestBranchBaseResolution:
    """Codex HIGH: a branch review with no --base must not silently diff only
    the last commit (HEAD~1); it resolves a real base or fails visibly."""

    def test_explicit_base_is_used_verbatim(self):
        assert delegate.review._resolve_branch_base("abc123", cwd=".") == "abc123"

    def test_resolves_first_available_candidate_merge_base(self, monkeypatch):
        seen = []

        def fake_git_or_none(args_list, cwd):
            # merge-base against @{upstream} "fails" (no upstream); origin/main hits.
            ref = args_list[-1]
            seen.append(ref)
            return "basesha123" if ref == "origin/main" else None

        monkeypatch.setattr(delegate.review, "_git_or_none", fake_git_or_none)
        assert delegate.review._resolve_branch_base(None, cwd=".") == "basesha123"
        assert seen[0] == "@{upstream}"  # most-specific candidate tried first

    def test_no_resolvable_base_fails_visibly(self, monkeypatch):
        monkeypatch.setattr(
            delegate.review, "_git_or_none", lambda args_list, cwd: None
        )
        try:
            delegate.review._resolve_branch_base(None, cwd=".")
        except delegate.review.ReviewDiffError as exc:
            assert "--base" in str(exc)
        else:
            raise AssertionError("expected ReviewDiffError when no base resolves")
