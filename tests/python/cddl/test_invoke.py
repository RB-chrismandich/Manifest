"""Foundational — LLM invocation seam (T005, FR-008/FR-012, research D4/D11)."""

import subprocess
import time

import pytest
from cddl import AbortError
from cddl.invoke import invoke_role
from cddl.loop import RunConfig


def cfg(**kw):
    return RunConfig(**{"cli": "claude", **kw})


def test_prompt_via_stdin_argv_fixed_flags(fake_runner_cls):
    runner = fake_runner_cls(["ok output"])
    out = invoke_role("sonnet", "big prompt " * 1000, cfg(), runner=runner)
    assert out == "ok output"
    call = runner.calls[0]
    assert call["argv"] == ["claude", "-p", "--model", "sonnet"]
    assert call["prompt"].startswith("big prompt")
    # ARG_MAX safety: the prompt must never ride argv (llm-invoke-stdin)
    assert all("big prompt" not in a for a in call["argv"])


def test_cli_seam_overrides_binary(fake_runner_cls):
    runner = fake_runner_cls(["x"])
    invoke_role("opus", "p", cfg(cli="mycli"), runner=runner)
    assert runner.calls[0]["argv"][0] == "mycli"


def test_timeout_is_failed_call_with_one_retry(fake_runner_cls):
    runner = fake_runner_cls(
        [subprocess.TimeoutExpired(cmd="claude", timeout=1), "recovered"]
    )
    out = invoke_role("sonnet", "p", cfg(), runner=runner, role_name="qa_critic")
    assert out == "recovered"
    assert len(runner.calls) == 2
    assert "[cddl retry]" in runner.calls[1]["prompt"]


def test_two_failures_abort(fake_runner_cls):
    runner = fake_runner_cls(
        [
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
        ]
    )
    with pytest.raises(AbortError, match="qa_critic"):
        invoke_role("sonnet", "p", cfg(), runner=runner, role_name="qa_critic")
    assert len(runner.calls) == 2


def test_nonzero_exit_is_failed_call(fake_runner_cls):
    runner = fake_runner_cls([(1, "", "boom"), "fine"])
    assert invoke_role("sonnet", "p", cfg(), runner=runner) == "fine"


def test_empty_output_is_failed_call(fake_runner_cls):
    runner = fake_runner_cls([(0, "   ", ""), "fine"])
    assert invoke_role("sonnet", "p", cfg(), runner=runner) == "fine"


def test_validator_failure_retries_with_notice(fake_runner_cls):
    runner = fake_runner_cls(["bad", "good"])
    out = invoke_role(
        "sonnet",
        "p",
        cfg(),
        runner=runner,
        validator=lambda o: None if o == "good" else "no verdict block",
    )
    assert out == "good"
    assert "no verdict block" in runner.calls[1]["prompt"]


def test_validator_failure_twice_aborts(fake_runner_cls):
    runner = fake_runner_cls(["bad", "bad"])
    with pytest.raises(AbortError):
        invoke_role("sonnet", "p", cfg(), runner=runner, validator=lambda o: "nope")


def test_deadline_expired_aborts_before_call(fake_runner_cls):
    runner = fake_runner_cls(["never used"])
    with pytest.raises(AbortError, match="deadline"):
        invoke_role("sonnet", "p", cfg(), runner=runner, deadline=time.monotonic() - 1)
    assert runner.calls == []


def test_timeout_capped_by_remaining_run_budget(fake_runner_cls):
    runner = fake_runner_cls(["ok"])
    invoke_role(
        "sonnet",
        "p",
        cfg(invoke_timeout_s=600),
        runner=runner,
        deadline=time.monotonic() + 5,
    )
    assert runner.calls[0]["timeout"] <= 5
