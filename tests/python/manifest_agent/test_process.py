from dataclasses import FrozenInstanceError

import pytest

from manifest_agent.models import CommandResult
from manifest_agent.process import CommandRunner, CommandTimeoutError


def test_runner_never_uses_a_shell():
    result = CommandRunner().run(("python3", "-c", "print('ok')"))

    assert isinstance(result, CommandResult)
    assert result.stdout.strip() == "ok"
    assert result.argv[0] == "python3"


def test_runner_rejects_string_commands():
    with pytest.raises(TypeError, match="argv must be a sequence"):
        CommandRunner().run("printf unsafe")  # type: ignore[arg-type]


def test_runner_kills_a_command_that_outlives_its_timeout_and_reports_partial_output():
    """A regression against Python's own subprocess quirk: `TimeoutExpired`
    carries the partial buffer it captured as raw bytes even under
    `text=True` -- decoding to `str` happens only on the successful-
    completion path. Building `CommandTimeoutError` from the undecoded value
    raised `TypeError: cannot use a string pattern on a bytes-like object`
    from `redact_text`, hiding the real timeout behind a generic native
    command failure."""
    with pytest.raises(CommandTimeoutError) as excinfo:
        CommandRunner().run(
            (
                "python3",
                "-c",
                "import sys, time; sys.stdout.write('partial-oauth-banner'); "
                "sys.stdout.flush(); time.sleep(5)",
            ),
            timeout=0.2,
        )

    error = excinfo.value
    assert isinstance(error.stdout, str)
    assert "partial-oauth-banner" in error.stdout
    assert error.timeout == 0.2


def test_runner_without_a_timeout_never_bounds_the_command():
    result = CommandRunner().run(("python3", "-c", "print('ok')"))

    assert result.stdout.strip() == "ok"


def test_runner_merges_environment_without_mutating_the_parent(monkeypatch):
    monkeypatch.setenv("MANIFEST_PARENT_VALUE", "parent")

    result = CommandRunner().run(
        (
            "python3",
            "-c",
            "import os; print(os.environ['MANIFEST_PARENT_VALUE'], "
            "os.environ['MANIFEST_CHILD_VALUE'])",
        ),
        env={"MANIFEST_CHILD_VALUE": "child"},
    )

    assert result.stdout.strip() == "parent child"


def test_runner_redacts_credentials_from_native_stderr():
    result = CommandRunner().run(
        (
            "python3",
            "-c",
            "import sys; sys.stderr.write('Authorization: Bearer native-secret')",
        )
    )

    assert "native-secret" not in result.stderr
    assert "[REDACTED]" in result.stderr


@pytest.mark.parametrize(
    "flag",
    [
        "--token super-secret",
        "--api-key API-KEY-VALUE",
        "--API_KEY UNDERSCORE-VALUE",
        "--password=PASSWORD-VALUE",
        "--credential CREDENTIAL-VALUE",
        "--credential=CREDENTIAL-EQUALS-VALUE",
        "--authorization AUTHORIZATION-VALUE",
        "--authorization=AUTHORIZATION-EQUALS-VALUE",
    ],
)
def test_runner_redacts_cli_flag_credentials_from_native_stderr(flag):
    result = CommandRunner().run(
        (
            "python3",
            "-c",
            "import sys; sys.stderr.write(sys.argv[1])",
            flag,
        )
    )

    assert flag.split()[-1].split("=")[-1] not in result.stderr
    assert "[REDACTED]" in result.stderr


def test_command_result_is_frozen():
    result = CommandResult(("true",), 0, "", "")

    with pytest.raises(FrozenInstanceError):
        result.returncode = 1  # type: ignore[misc]
