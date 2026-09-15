#!/usr/bin/env python3
"""Install and authenticate exactly one native harness CLI for live parity.

The protected live-parity job proves that a real, licensed, authenticated CLI
reaches READY parity. That requires credentials, so this step is the one place
in the pipeline that touches them, and it is deliberately committed code rather
than shell hidden inside a secret: a credential-handling step must be reviewable.

Contract per harness (registry below, no code switches on harness names):

* the credential comes from exactly one protected environment secret;
* the third-party installer runs BEFORE the credential exists in its
  environment, so a compromised installer cannot read it;
* authentication is either an environment variable exported through
  ``GITHUB_ENV`` for the rest of the job, or an owner-only (0600) credential
  file the CLI reads itself — never both;
* the CLI's own probe must succeed, so an unusable credential fails the step
  instead of reporting a green "installed" result;
* the credential value is never printed.

A missing secret is an explicit ``BLOCKED`` failure. A harness the registry does
not know is refused before any secret is read.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

Runner = Callable[[Sequence[str], Mapping[str, str]], int]
# Quoted return type: this alias is evaluated at import time, so it must parse
# on an older bare `python3` too.
Locator = Callable[[str, Mapping[str, str]], "str | None"]


# The workflow resolves the matrix harness's protected secret and hands it to
# this step under one generic name, so a job only ever sees its own credential.
CREDENTIAL_VARIABLE = "LIVE_HARNESS_CREDENTIAL"


def _download_and_run(url: str) -> tuple[str, ...]:
    """Fetch an upstream installer to a file, then run it.

    Piping a download straight into a shell is forbidden by the repository's
    shell standards; these upstream installers publish no checksum, so the
    download is materialized first and executed as a file.
    """
    script = (
        "set -euo pipefail; "
        'installer="$(mktemp)"; '
        f'curl -fsSL "{url}" -o "$installer"; '
        'bash "$installer"; '
        'rm -f "$installer"'
    )
    return ("bash", "-c", script)


@dataclass(frozen=True)
class Harness:
    """One backend's install/authenticate/probe contract."""

    name: str
    secret_name: str
    binary: str  # executable that must exist on PATH once the installer ran
    install_argv: tuple[str, ...]
    verify_argv: tuple[str, ...]
    credential_env: str | None = None
    credential_path: PurePosixPath | None = None
    settings: tuple[tuple[PurePosixPath, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (self.credential_env is None) == (self.credential_path is None):
            raise ValueError(
                f"{self.name}: authenticate through exactly one of an environment"
                " variable or a credential file"
            )


_ANTIGRAVITY_SETTINGS = json.dumps({"modelProvider": "gemini"}, indent=2) + "\n"

HARNESSES: dict[str, Harness] = {
    harness.name: harness
    for harness in (
        Harness(
            name="claude",
            secret_name="LIVE_CLAUDE_CREDENTIAL",
            binary="claude",
            install_argv=("npm", "install", "-g", "@anthropic-ai/claude-code"),
            verify_argv=("claude", "-p", "reply with ok"),
            credential_env="ANTHROPIC_API_KEY",
        ),
        Harness(
            name="codex",
            secret_name="LIVE_CODEX_CREDENTIAL",
            binary="codex",
            install_argv=("npm", "install", "-g", "@openai/codex"),
            verify_argv=("codex", "login", "status"),
            credential_env="OPENAI_API_KEY",
        ),
        Harness(
            name="gemini",
            secret_name="LIVE_GEMINI_CREDENTIAL",
            binary="gemini",
            install_argv=("npm", "install", "-g", "@google/gemini-cli"),
            verify_argv=("gemini", "-p", "reply with ok"),
            credential_env="GEMINI_API_KEY",
        ),
        Harness(
            name="cursor",
            secret_name="LIVE_CURSOR_CREDENTIAL",
            binary="cursor-agent",
            install_argv=_download_and_run("https://cursor.com/install"),
            verify_argv=("cursor-agent", "status"),
            credential_env="CURSOR_API_KEY",
        ),
        # agy reads only GEMINI_API_KEY, and only when modelProvider is pinned to
        # gemini in its settings file: the variable alone has no effect.
        Harness(
            name="antigravity",
            secret_name="LIVE_ANTIGRAVITY_CREDENTIAL",
            binary="agy",
            install_argv=_download_and_run("https://antigravity.google/cli/install.sh"),
            verify_argv=("agy", "models"),
            credential_env="GEMINI_API_KEY",
            settings=(
                (
                    PurePosixPath(".gemini/antigravity-cli/settings.json"),
                    _ANTIGRAVITY_SETTINGS,
                ),
            ),
        ),
        # The Devin CLI reads a persistent token file; it has no credential
        # environment variable, so the secret never enters the job environment.
        Harness(
            name="devin",
            # The secret's value is the full credentials.toml document.
            secret_name="LIVE_DEVIN_CREDENTIAL",
            binary="devin",
            # The official installer ends by running an interactive `devin
            # setup`, which cannot complete on a runner, so the installer's exit
            # code is advisory: what matters is the binary landing on PATH.
            install_argv=_download_and_run("https://cli.devin.ai/install.sh"),
            verify_argv=("devin", "models", "list"),
            credential_path=PurePosixPath(".local/share/devin/credentials.toml"),
        ),
    )
}


def _write_owner_only(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(path, 0o600)


def _resolved_within(home: Path, relative: PurePosixPath) -> Path:
    """Return ``home/relative``, refusing any path that escapes ``home``."""
    root = home.resolve()
    candidate = (root / Path(relative)).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"credential path escaped the harness home: {relative}")
    return candidate


def provision(
    harness: Harness,
    credential: str,
    *,
    home: Path,
    github_env: Path,
    credential_path_override: PurePosixPath | Path | None = None,
) -> dict[str, str]:
    """Place the credential where the CLI reads it; return its job environment.

    Environment-authenticated harnesses get exactly one variable, appended to
    ``GITHUB_ENV`` so later steps in the job inherit it. File-authenticated
    harnesses get an owner-only file and contribute nothing to the environment.
    """
    home.mkdir(parents=True, exist_ok=True)
    for relative, content in harness.settings:
        _write_owner_only(_resolved_within(home, relative), content)

    relative_credential = credential_path_override
    if relative_credential is None:
        relative_credential = harness.credential_path
    if relative_credential is not None:
        _write_owner_only(
            _resolved_within(home, PurePosixPath(relative_credential)), credential
        )

    if harness.credential_env is None:
        return {}
    with github_env.open("a", encoding="utf-8") as handle:
        handle.write(f"{harness.credential_env}={credential}\n")
    return {harness.credential_env: credential}


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    try:
        return subprocess.run(list(argv), env=dict(env), check=False).returncode
    except FileNotFoundError:
        # A CLI absent after its own installer ran is a failed setup, not a crash.
        print(f"live_harness_setup.py: {argv[0]} is not on PATH", file=sys.stderr)
        return 127


def _sanitized(environ: Mapping[str, str], credential: str) -> dict[str, str]:
    """The job environment with every copy of the credential removed.

    The runner still holds the raw secret bytes, so whitespace-padded and
    wrapped copies (`"Bearer <secret>"`, a value set from a file with a
    trailing newline) must drop too: exact comparison against the stripped
    credential would leave them readable by the third-party installer.
    """
    secret = credential.strip()
    return {
        key: value
        for key, value in environ.items()
        if value.strip() != secret and secret not in value
    }


def _which(binary: str, env: Mapping[str, str]) -> str | None:
    return shutil.which(binary, path=env.get("PATH"))


def _fail(message: str) -> None:
    print(f"live_harness_setup.py: {message}", file=sys.stderr)


def _selected(argv: Sequence[str] | None) -> Harness | None:
    parser = argparse.ArgumentParser(
        prog="live_harness_setup.py",
        description="Install and authenticate one native harness CLI for live parity.",
    )
    parser.add_argument(
        "--harness",
        required=True,
        help=f"harness to provision ({', '.join(sorted(HARNESSES))})",
    )
    requested = parser.parse_args(argv).harness
    harness = HARNESSES.get(requested)
    if harness is None:
        _fail(
            f"unknown harness {requested!r};"
            f" known harnesses: {', '.join(sorted(HARNESSES))}"
        )
    return harness


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    locator: Locator | None = None,
) -> int:
    """Return 0 only when the harness is installed AND its probe authenticated.

    2 = unknown harness; 1 = missing secret, absent CLI, or a failing probe.
    """
    harness = _selected(argv)
    if harness is None:
        return 2

    environ = os.environ if environ is None else environ
    runner = _subprocess_runner if runner is None else runner
    locator = _which if locator is None else locator

    credential = (environ.get(CREDENTIAL_VARIABLE) or "").strip()
    if not credential:
        _fail(
            f"BLOCKED: protected secret {harness.secret_name}"
            f" is required to authenticate {harness.name}"
        )
        return 1

    base = _sanitized(environ, credential)
    # Installer exit codes are advisory: some official installers end with an
    # interactive setup step that cannot complete on a runner. The binary
    # landing on PATH is the fact that matters, and the probe below is what
    # proves the CLI is genuinely usable.
    runner(harness.install_argv, base)
    if locator(harness.binary, base) is None:
        _fail(f"BLOCKED: {harness.binary} is absent after installing {harness.name}")
        return 1

    exported = provision(
        harness,
        credential,
        home=Path(environ["HOME"]),
        github_env=Path(environ["GITHUB_ENV"]),
    )
    if runner(harness.verify_argv, {**base, **exported}) != 0:
        _fail(
            f"BLOCKED: {harness.name} is installed but its authentication probe failed"
        )
        return 1

    print(f"live_harness_setup.py: {harness.name} installed and authenticated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
