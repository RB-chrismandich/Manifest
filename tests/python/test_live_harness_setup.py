"""Per-harness live-parity setup: credential scoping, no-leak, real auth probes.

The protected live-parity job must install exactly one native CLI, authenticate
it from exactly one protected secret, and prove the authentication with the
harness's own probe. These tests pin the properties a credential-handling step
cannot be allowed to lose: the installer never sees the credential, the secret
value never reaches stdout/stderr or a world-readable file, a missing secret is
an explicit BLOCKED error rather than a silent skip, and a harness the registry
does not know is refused before any secret is read.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from tools.live_harness_setup import (
    CREDENTIAL_VARIABLE,
    HARNESSES,
    main,
    provision,
)

_SECRET = "cred-value-never-logged"


class _Runner:
    """Records dispatched argv plus the environment each command received."""

    def __init__(self, failures: dict[str, int] | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
        self._failures = failures or {}

    def __call__(self, argv, env):
        self.calls.append((tuple(argv), dict(env)))
        return self._failures.get(argv[0], 0)

    @property
    def dispatched(self) -> list[tuple[str, ...]]:
        return [argv for argv, _ in self.calls]


def _run(
    harness: str,
    tmp_path: Path,
    *,
    secret: str | None = _SECRET,
    runner=None,
    installed: bool = True,
):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    github_env = tmp_path / "github.env"
    github_env.touch()
    environment = {"HOME": str(home), "GITHUB_ENV": str(github_env)}
    if secret is not None:
        environment[CREDENTIAL_VARIABLE] = secret
    runner = runner if runner is not None else _Runner()
    status = main(
        ["--harness", harness],
        environ=environment,
        runner=runner,
        locator=lambda binary, _env: f"/usr/local/bin/{binary}" if installed else None,
    )
    return status, runner, home, github_env


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_every_harness_installs_then_authenticates_then_probes(
    harness: str, tmp_path: Path
) -> None:
    status, runner, _, _ = _run(harness, tmp_path)

    assert status == 0
    install, verify = HARNESSES[harness].install_argv, HARNESSES[harness].verify_argv
    assert runner.dispatched == [tuple(install), tuple(verify)]


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_installer_never_receives_the_credential(harness: str, tmp_path: Path) -> None:
    _, runner, _, _ = _run(harness, tmp_path)

    install_env = runner.calls[0][1]
    assert _SECRET not in install_env.values()
    verify_env = runner.calls[1][1]
    assert any(value == _SECRET for value in verify_env.values()) or (
        HARNESSES[harness].credential_path is not None
    )


@pytest.mark.parametrize("stored", (f"{_SECRET}\n", f"  {_SECRET}  "))
def test_installer_never_receives_a_whitespace_padded_credential(
    stored: str, tmp_path: Path
) -> None:
    """GitHub keeps the raw bytes; a secret set from a file carries a newline."""
    _, runner, _, _ = _run("claude", tmp_path, secret=stored)

    install_env = runner.calls[0][1]
    assert not any(_SECRET in value for value in install_env.values())


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_missing_secret_is_an_explicit_blocked_error(
    harness: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, runner, _, _ = _run(harness, tmp_path, secret=None)

    assert status == 1
    assert runner.dispatched == []
    captured = capsys.readouterr()
    assert "BLOCKED" in captured.err
    assert HARNESSES[harness].secret_name in captured.err


def test_unknown_harness_is_refused_before_any_secret_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Runner()
    status = main(
        ["--harness", "not-a-harness"],
        environ={"HOME": str(tmp_path), "GITHUB_ENV": str(tmp_path / "env")},
        runner=runner,
    )

    assert status == 2
    assert runner.dispatched == []
    assert "not-a-harness" in capsys.readouterr().err


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_credential_value_never_appears_on_stdout_or_stderr(
    harness: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(harness, tmp_path)

    captured = capsys.readouterr()
    assert _SECRET not in captured.out
    assert _SECRET not in captured.err


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_credential_files_are_owner_only(harness: str, tmp_path: Path) -> None:
    _, _, home, _ = _run(harness, tmp_path)

    relative = HARNESSES[harness].credential_path
    if relative is None:
        pytest.skip(f"{harness} authenticates through the environment")
    written = home / relative
    assert written.read_text(encoding="utf-8") == _SECRET
    mode = stat.S_IMODE(written.stat().st_mode)
    assert mode == 0o600, oct(mode)


def test_devin_credential_stays_in_its_file_and_out_of_the_job_environment(
    tmp_path: Path,
) -> None:
    _, _, home, github_env = _run("devin", tmp_path)

    assert (home / HARNESSES["devin"].credential_path).exists()
    assert _SECRET not in github_env.read_text(encoding="utf-8")


def test_antigravity_selects_the_gemini_provider_it_requires(tmp_path: Path) -> None:
    _, _, home, github_env = _run("antigravity", tmp_path)

    settings = json.loads(
        (home / ".gemini/antigravity-cli/settings.json").read_text(encoding="utf-8")
    )
    assert settings["modelProvider"] == "gemini"
    assert f"GEMINI_API_KEY={_SECRET}" in github_env.read_text(encoding="utf-8")


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_environment_authenticated_harnesses_export_exactly_one_variable(
    harness: str, tmp_path: Path
) -> None:
    _, _, _, github_env = _run(harness, tmp_path)

    exported = [
        line
        for line in github_env.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected = HARNESSES[harness].credential_env
    if expected is None:
        assert exported == []
    else:
        assert exported == [f"{expected}={_SECRET}"]


def test_a_failing_probe_fails_the_step(tmp_path: Path) -> None:
    runner = _Runner(failures={HARNESSES["claude"].verify_argv[0]: 3})

    status, runner, _, _ = _run("claude", tmp_path, runner=runner)

    assert status == 1
    assert len(runner.dispatched) == 2


def test_an_interactive_installer_tail_does_not_fail_a_working_install(
    tmp_path: Path,
) -> None:
    # The Devin installer ends by running an interactive `devin setup`, which
    # cannot complete on a runner; the binary landing on PATH plus a passing
    # probe is what proves the harness usable.
    runner = _Runner(failures={HARNESSES["devin"].install_argv[0]: 1})

    status, runner, _, _ = _run("devin", tmp_path, runner=runner)

    assert status == 0
    assert len(runner.dispatched) == 2


def test_a_missing_binary_after_install_is_blocked_before_the_probe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, runner, _, _ = _run("claude", tmp_path, installed=False)

    assert status == 1
    assert len(runner.dispatched) == 1
    assert "BLOCKED" in capsys.readouterr().err


def test_provision_refuses_a_path_escaping_the_home_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        provision(
            HARNESSES["devin"],
            _SECRET,
            home=tmp_path / "home",
            github_env=tmp_path / "env",
            credential_path_override=Path("../escaped/credentials.toml"),
        )
