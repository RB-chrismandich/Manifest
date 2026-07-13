"""US1/US2/US4 — two-phase state machine (T017/T025/T032).

All model access through FakeRunner. Invocation order contract:
phase 1 round: qa_critic, arch_critic; phase 2 iteration: implementer,
[project verification], qa_critic, arch_critic.
"""

import json
import subprocess

from cddl.loop import RunConfig, start_run
from cddl.persistence import RunStore


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def staged(repo):
    return git(repo, "diff", "--cached", "--name-only").splitlines()


def run(target, runner, state_root, roles_dir, **cfg):
    config = RunConfig(cli="stub-cli", **cfg)
    return start_run(
        target, config, state_root=state_root, prompts_dir=roles_dir, runner=runner
    )


def state_of(state_root, repo, outcome):
    return RunStore(state_root, repo, run_id=outcome.run_id).read_state()


def both_complete(verdict):
    return [verdict("qa_critic", "complete"), verdict("arch_critic", "complete")]


GREET = [("greet.py", "print('hello')\n")]


# --- US1: phase-2 loop (T017) ---


def test_dual_approval_success_and_staged(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    head_before = git(fixture_repo, "rev-parse", "HEAD").strip()
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert outcome.status == "success"
    assert outcome.exit_code == 0
    assert staged(fixture_repo) == ["greet.py"]
    # no commit/push/merge ever (US1 acceptance 3)
    assert git(fixture_repo, "rev-parse", "HEAD").strip() == head_before

    state = state_of(state_root, fixture_repo, outcome)
    final = state["iterations"][-1]
    assert final["verdicts"]["qa_critic"]["decision"] == "approve"
    assert final["verdicts"]["arch_critic"]["decision"] == "approve"
    assert state["status"] == "success"
    assert state["written_paths"] == ["greet.py"]


def test_success_stages_only_final_approved_candidate(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    # Iteration 1 writes an extra file and is REJECTED; iteration 2's approved
    # candidate touches only greet.py. FR-011: staged = critic-approved, so
    # the leftover must stay unstaged (and never be reverted — clarification Q1).
    finding = [{"title": "extra-file", "detail": "drop the helper"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate([("greet.py", "print('v1')\n"), ("extra.py", "junk\n")]),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "approve"),
            candidate([("greet.py", "print('v2')\n")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert outcome.status == "success"
    assert staged(fixture_repo) == ["greet.py"]  # never the rejected leftover
    assert (fixture_repo / "extra.py").exists()  # left applied, unstaged
    state = state_of(state_root, fixture_repo, outcome)
    assert state["staged_paths"] == ["greet.py"]
    assert "extra.py" in state["written_paths"]
    report = (
        RunStore(state_root, fixture_repo, run_id=outcome.run_id).run_dir / "report.md"
    ).read_text()
    assert "leftovers" in report and "extra.py" in report
    assert "rm -f 'extra.py'" in report  # loop-created: discard = remove


def test_approved_deletion_of_untracked_loop_file_succeeds(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    # Iteration 1 creates helper.py (never tracked); the approved iteration 2
    # deletes it again — staging must not die on the phantom pathspec.
    finding = [{"title": "drop-helper", "detail": "not needed"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate([("greet.py", "print('v1')\n"), ("helper.py", "tmp\n")]),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "approve"),
            candidate([("greet.py", "print('v2')\n"), ("helper.py", "", "delete")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert outcome.status == "success"
    assert staged(fixture_repo) == ["greet.py"]
    assert not (fixture_repo / "helper.py").exists()


def test_backup_preserves_preexisting_dirty_content(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    # --allow-dirty: the operator's uncommitted edit must be recoverable from
    # the per-iteration backup after the loop overwrites the file.
    dirty = fixture_repo / "README.md"
    dirty.write_text("my uncommitted precious edit\n")
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate([("README.md", "loop rewrote this\n")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(
        fixture_repo, runner, state_root, roles_dir, verify_cmd="true", allow_dirty=True
    )
    assert outcome.status == "success"
    backup = (
        RunStore(state_root, fixture_repo, run_id=outcome.run_id).run_dir
        / "iterations"
        / "1"
        / "backup"
        / "README.md"
    )
    assert backup.read_text() == "my uncommitted precious edit\n"
    assert (fixture_repo / "README.md").read_text() == "loop rewrote this\n"


def test_report_restore_uses_backup_for_preexisting_files(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    # --allow-dirty + failed run: the discard instruction must restore the
    # pre-run content from the backup, never `git checkout` (which would
    # destroy the operator's uncommitted edits).
    (fixture_repo / "README.md").write_text("my uncommitted edit\n")
    finding = [{"title": "bad", "detail": "x"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate([("README.md", "loop version\n")]),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "reject", finding),
        ]
    )
    outcome = run(
        fixture_repo,
        runner,
        state_root,
        roles_dir,
        verify_cmd="true",
        max_iterations=1,
        allow_dirty=True,
    )
    assert outcome.status == "ceiling_failure"
    store = RunStore(state_root, fixture_repo, run_id=outcome.run_id)
    report = (store.run_dir / "report.md").read_text()
    assert "cp '" in report and "backup/README.md" in report
    assert "git checkout" not in report
    backup = store.run_dir / "iterations" / "1" / "backup" / "README.md"
    assert backup.read_text() == "my uncommitted edit\n"


def test_implementer_sees_earlier_written_files(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    # Leftovers are never auto-reverted (clarification Q1); instead they are
    # disclosed so the implementer can manage them via cddl-delete blocks.
    finding = [{"title": "x", "detail": "y"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate([("greet.py", "v1\n"), ("extra.py", "junk\n")]),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "approve"),
            candidate([("greet.py", "v2\n")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    impl2_prompt = runner.calls[5]["prompt"]
    assert "loop wrote in earlier iterations" in impl2_prompt
    assert "extra.py" in impl2_prompt


def test_reject_findings_feed_next_iteration_context(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    finding = {"title": "missing-validation", "detail": "no input check on name"}
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "reject", [finding]),
            verdict("arch_critic", "approve"),
            candidate([("greet.py", "print('hello, safely')\n")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert outcome.status == "success"
    # call order: qa, arch, impl1, qa, arch, impl2, qa, arch
    impl2_prompt = runner.calls[5]["prompt"]
    assert "missing-validation" in impl2_prompt
    assert "no input check on name" in impl2_prompt


def test_ceiling_exhaustion_leaves_candidate_unstaged(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    finding = [{"title": "still-wrong", "detail": "nope"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "reject", finding),
        ]
    )
    outcome = run(
        fixture_repo, runner, state_root, roles_dir, verify_cmd="true", max_iterations=1
    )
    assert outcome.status == "ceiling_failure"
    assert outcome.exit_code == 5
    assert (fixture_repo / "greet.py").exists()  # applied…
    assert staged(fixture_repo) == []  # …but never staged (FR-011)


def test_verification_failure_skips_critics_and_feeds_back(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    runner = fake_runner_cls([*both_complete(verdict), candidate(GREET)])
    outcome = run(
        fixture_repo,
        runner,
        state_root,
        roles_dir,
        verify_cmd="python3 -c 'import sys; sys.exit(2)'",
        max_iterations=1,
    )
    assert outcome.status == "ceiling_failure"
    # critics were never invoked on failing work (FR-009): qa, arch, impl only
    assert len(runner.calls) == 3
    state = state_of(state_root, fixture_repo, outcome)
    it = state["iterations"][0]
    assert it["verification"]["ran"] is True
    assert it["verification"]["passed"] is False
    assert any(d["source"] == "verification" for d in it["deficiencies"])


def test_stalled_candidate_counts_and_never_succeeds(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    finding = [{"title": "bad", "detail": "x"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "approve"),
            candidate(GREET),  # byte-identical -> stall
        ]
    )
    outcome = run(
        fixture_repo, runner, state_root, roles_dir, verify_cmd="true", max_iterations=2
    )
    assert outcome.status == "ceiling_failure"
    # stall skipped verification + critics: qa, arch, impl, qa, arch, impl = 6 calls
    assert len(runner.calls) == 6
    state = state_of(state_root, fixture_repo, outcome)
    assert state["iterations"][1]["stalled"] is True


def test_run_deadline_aborts(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict
):
    runner = fake_runner_cls(both_complete(verdict))
    outcome = run(fixture_repo, runner, state_root, roles_dir, run_timeout_s=0.000001)
    assert outcome.status == "aborted"
    assert outcome.exit_code == 7


def test_unrecoverable_critic_aborts_fail_closed(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            "garbage without a block",
            "still garbage",
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert outcome.status == "aborted"
    assert staged(fixture_repo) == []  # a dead critic never counts as approval
    # US4/quickstart: the failing critic's raw output is persisted per attempt,
    # so a double parse failure still leaves evidence on disk to diagnose.
    store = RunStore(state_root, fixture_repo, run_id=outcome.run_id)
    raw = (store.run_dir / "iterations" / "1" / "qa_critic.md").read_text()
    assert "still garbage" in raw  # last failing attempt


def test_phase1_critic_abort_persists_raw_attempts(
    fixture_repo, state_root, roles_dir, fake_runner_cls
):
    runner = fake_runner_cls(["not a verdict", "still not a verdict"])
    outcome = run(fixture_repo, runner, state_root, roles_dir)
    assert outcome.status == "aborted"
    store = RunStore(state_root, fixture_repo, run_id=outcome.run_id)
    raw = (store.run_dir / "clarify" / "round-1-qa_critic.md").read_text()
    assert "still not a verdict" in raw


def test_unresolvable_target_mutates_no_state(
    tmp_path, state_root, roles_dir, fake_runner_cls
):
    import pytest
    from cddl import PreflightError

    empty = tmp_path / "no-layout"
    empty.mkdir()
    runner = fake_runner_cls(["never used"])
    with pytest.raises(PreflightError):
        run(empty, runner, state_root, roles_dir)
    # US3 scenario 3: zero model calls, zero state mutations on refusal
    assert runner.calls == []
    assert list(state_root.iterdir()) == []


def test_answer_refused_when_not_awaiting(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    import pytest
    from cddl import PreflightError
    from cddl.loop import answer_run

    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    done = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert done.status == "success"
    with pytest.raises(PreflightError, match="not awaiting"):
        answer_run(
            fixture_repo,
            done.run_id,
            "late answer",
            RunConfig(cli="stub-cli"),
            state_root=state_root,
            prompts_dir=roles_dir,
            runner=fake_runner_cls([]),
        )


def test_answer_refuses_empty_answers(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict
):
    import pytest
    from cddl import PreflightError
    from cddl.loop import answer_run

    parked = run(
        fixture_repo,
        fake_runner_cls(
            [
                verdict("qa_critic", "questions", [QUESTION]),
                verdict("arch_critic", "complete"),
            ]
        ),
        state_root,
        roles_dir,
    )
    assert parked.status == "questions_pending"
    with pytest.raises(PreflightError, match="empty"):
        answer_run(
            fixture_repo,
            parked.run_id,
            "   \n",
            RunConfig(cli="stub-cli"),
            state_root=state_root,
            prompts_dir=roles_dir,
            runner=fake_runner_cls([]),
        )


# --- US2: clarification gate (T025) ---

QUESTION = {"title": "size-limit", "detail": "what is the maximum upload size?"}


def test_open_questions_park_the_run_with_no_implementation(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict
):
    runner = fake_runner_cls(
        [
            verdict("qa_critic", "questions", [QUESTION]),
            verdict("arch_critic", "complete"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir)
    assert outcome.status == "questions_pending"
    assert outcome.exit_code == 3
    # zero implementation output of any kind before the gate passes
    state = state_of(state_root, fixture_repo, outcome)
    assert state["iterations"] == []
    assert git(fixture_repo, "status", "--porcelain") == ""
    store = RunStore(state_root, fixture_repo, run_id=outcome.run_id)
    questions_md = (store.run_dir / "questions.md").read_text()
    assert "size-limit" in questions_md
    assert "qa_critic" in questions_md and "arch_critic" in questions_md


def test_dual_signal_required_one_complete_one_questions_still_pending(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict
):
    runner = fake_runner_cls(
        [
            verdict("qa_critic", "complete"),
            verdict("arch_critic", "questions", [QUESTION]),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir)
    assert outcome.status == "questions_pending"  # FR-003: both must complete


def test_answers_reach_gate_and_every_iteration_context(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    from cddl.loop import answer_run

    first = fake_runner_cls(
        [
            verdict("qa_critic", "questions", [QUESTION]),
            verdict("arch_critic", "complete"),
        ]
    )
    parked = run(fixture_repo, first, state_root, roles_dir)
    assert parked.status == "questions_pending"

    second = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = answer_run(
        fixture_repo,
        parked.run_id,
        "The maximum upload size is 10MB.",
        RunConfig(cli="stub-cli", verify_cmd="true"),
        state_root=state_root,
        prompts_dir=roles_dir,
        runner=second,
    )
    assert outcome.status == "success"
    assert outcome.run_id == parked.run_id  # same run, re-entered
    # answers are part of the round-2 critic context AND the implementer context
    assert "10MB" in second.calls[0]["prompt"]  # qa_critic round 2
    assert "10MB" in second.calls[2]["prompt"]  # implementer iteration 1
    store = RunStore(state_root, fixture_repo, run_id=parked.run_id)
    assert "10MB" in (store.run_dir / "context.md").read_text()
    assert (store.run_dir / "answers-1.md").read_text().startswith("The maximum")


def test_round_limit_exhaustion_is_gate_failure_with_zero_code(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict
):
    runner = fake_runner_cls(
        [
            verdict("qa_critic", "questions", [QUESTION]),
            verdict("arch_critic", "questions", [QUESTION]),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, max_rounds=1)
    assert outcome.status == "gate_failure"
    assert outcome.exit_code == 4
    assert "size-limit" in outcome.message  # unresolved questions listed (FR-004)
    state = state_of(state_root, fixture_repo, outcome)
    assert state["iterations"] == []
    assert git(fixture_repo, "status", "--porcelain") == ""


# --- US4: diagnosable run history (T032) ---


def test_iteration_artifacts_complete_after_full_run(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    it_dir = (
        RunStore(state_root, fixture_repo, run_id=outcome.run_id).run_dir
        / "iterations"
        / "1"
    )
    for artifact in (
        "candidate.md",
        "files.json",
        "verify.log",
        "qa_critic.md",
        "arch_critic.md",
        "verdicts.json",
    ):
        assert (it_dir / artifact).is_file(), f"missing {artifact}"
    state = state_of(state_root, fixture_repo, outcome)
    it = state["iterations"][0]
    assert it["started_at"] and it["ended_at"]  # timestamps (US4 scenario 1)


def test_ceiling_report_names_blocking_critic_and_discard_steps(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    finding = [{"title": "unbounded-loop", "detail": "no exit condition"}]
    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "reject", finding),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(
        fixture_repo, runner, state_root, roles_dir, verify_cmd="true", max_iterations=1
    )
    assert outcome.status == "ceiling_failure"
    report = (
        RunStore(state_root, fixture_repo, run_id=outcome.run_id).run_dir / "report.md"
    ).read_text()
    assert "qa_critic" in report  # the blocking critic (US4 scenario 2)
    assert "unbounded-loop" in report  # its outstanding deficiency
    assert "UNSTAGED" in report
    # greet.py did not exist pre-run: discard = remove (no pre-image to restore)
    assert "rm -f 'greet.py'" in report  # discard instructions (FR-011)
    blocking_section = report.split("## Blocking critics")[1]
    assert "qa_critic" in blocking_section
    assert "arch_critic" not in blocking_section  # approving critic never blocks


def test_audit_event_per_transition(
    fixture_repo,
    state_root,
    roles_dir,
    fake_runner_cls,
    verdict,
    candidate,
    monkeypatch,
    tmp_path,
):
    import cddl.persistence as persistence

    events_file = tmp_path / "events.jsonl"
    stub = tmp_path / "audit_log.sh"
    stub.write_text(
        '#!/usr/bin/env bash\n[ "$1" = append ] || exit 0\n'
        f'printf \'%s\\n\' "$2" >> "{events_file}"\n'
    )
    stub.chmod(0o755)
    monkeypatch.setattr(persistence, "AUDIT_SCRIPT", stub)

    runner = fake_runner_cls(
        [
            *both_complete(verdict),
            candidate(GREET),
            verdict("qa_critic", "reject", [{"title": "x", "detail": "y"}]),
            verdict("arch_critic", "approve"),
            candidate([("greet.py", "print('better')\n")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    assert outcome.status == "success"
    events = [
        json.loads(line)["event"] for line in events_file.read_text().splitlines()
    ]
    assert events[0] == "run_started"
    assert "gate_passed" in events
    assert "iteration_rejected" in events
    assert events[-1] == "success"


def test_interrupted_run_leaves_diagnosable_state(
    fixture_repo, state_root, roles_dir, fake_runner_cls, verdict, candidate
):
    import pytest

    class Crash(BaseException):
        """Simulates the process dying mid-run (not an AbortError)."""

    runner = fake_runner_cls(
        [*both_complete(verdict), candidate(GREET), Crash("power loss")]
    )
    with pytest.raises(Crash):
        run(fixture_repo, runner, state_root, roles_dir, verify_cmd="true")
    store = RunStore.latest(state_root, fixture_repo)
    state = store.read_state()
    # the incomplete state is evident without re-running (spec edge case)
    assert state["status"] == "running"
    assert state["finished_at"] is None
    assert state["iterations"][0]["started_at"]
    assert (store.run_dir / "iterations" / "1" / "candidate.md").is_file()
