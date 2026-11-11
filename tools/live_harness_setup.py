#!/usr/bin/env python3
"""Install and authenticate exactly one native harness CLI for live parity.

The protected live-parity job proves that a real, licensed, authenticated CLI
reaches READY parity. That requires credentials, so this helper is the one place
in the pipeline that touches them, and it is deliberately committed code rather
than shell hidden inside a secret: a credential-handling step must be reviewable.

The work is two subcommands, run as two separate workflow steps:

* ``install`` fetches and installs the CLI. It refuses to run when the
  credential is present, so no process of that step, and nothing it downloads,
  ever shares an environment or a process tree with the secret.
* ``authenticate`` runs afterwards with the credential, places it where the CLI
  reads it, and proves it with the CLI's own probe.

Contract per harness (registry below, no code switches on harness names):

* what gets installed is pinned and verified before it runs: an npm CLI comes
  from a committed lockfile (``npm ci`` checks every package's integrity hash),
  any other CLI from a versioned archive whose SHA-256 is committed here.
  Nothing is fetched from a mutable "latest" channel, and no upstream installer
  script is executed. A digest mismatch or an unpinned platform is BLOCKED;
* the credential comes from exactly one protected environment secret;
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
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

Runner = Callable[[Sequence[str], Mapping[str, str]], int]
# Quoted return type: this alias is evaluated at import time, so it must parse
# on an older bare `python3` too.
Locator = Callable[[str, Mapping[str, str]], "str | None"]
Fetcher = Callable[[str, Path], None]


# The workflow resolves the matrix harness's protected secret and hands it to
# this step under one generic name, so a job only ever sees its own credential.
CREDENTIAL_VARIABLE = "LIVE_HARNESS_CREDENTIAL"


# Every pin targets the hosted runner the live-parity job uses. Another platform
# is BLOCKED rather than served an archive built for a different one.
PINNED_PLATFORM = ("Linux", "x86_64")
_LOCKFILES = Path(__file__).resolve().parent / "live_harness"
_INSTALL_ROOT = PurePosixPath(".local/share/manifest-live-harness")
_BIN_DIR = PurePosixPath(".local/bin")


@dataclass(frozen=True)
class NpmLock:
    """An npm CLI installed with ``npm ci`` from a committed lockfile."""

    project: str  # directory under tools/live_harness/ holding the lockfile
    links: tuple[tuple[str, str], ...]  # (name on PATH, path under the project)


@dataclass(frozen=True)
class PinnedArchive:
    """A versioned upstream tar.gz verified against a committed SHA-256."""

    version: str
    url: str
    sha256: str
    links: tuple[tuple[str, str], ...]  # (name on PATH, path inside the archive)
    strip_components: int = 0

    def __post_init__(self) -> None:
        if not self.url.startswith("https://") or self.version not in self.url:
            raise ValueError(f"archive URL must be https and versioned: {self.url}")
        if len(self.sha256) != 64 or set(self.sha256) - set("0123456789abcdef"):
            raise ValueError(f"archive digest must be a lowercase SHA-256: {self.url}")


@dataclass(frozen=True)
class Harness:
    """One backend's install/authenticate/probe contract."""

    name: str
    secret_name: str
    binary: str  # executable that must exist on PATH once the install ran
    source: NpmLock | PinnedArchive
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
            source=NpmLock("claude", (("claude", "node_modules/.bin/claude"),)),
            verify_argv=("claude", "-p", "reply with ok"),
            credential_env="ANTHROPIC_API_KEY",
        ),
        Harness(
            name="codex",
            secret_name="LIVE_CODEX_CREDENTIAL",
            binary="codex",
            source=NpmLock("codex", (("codex", "node_modules/.bin/codex"),)),
            verify_argv=("codex", "login", "status"),
            credential_env="OPENAI_API_KEY",
        ),
        Harness(
            name="cursor",
            secret_name="LIVE_CURSOR_CREDENTIAL",
            binary="cursor-agent",
            source=PinnedArchive(
                version="2026.11.11-043ef28",
                url="https://downloads.cursor.com/lab/2026.11.11-043ef28/linux/x64/agent-cli-package.tar.gz",
                sha256="5d82bd6e6f090b1804b8284fdc68050f0d588183cafc9d78365379e218ed650c",
                links=(("cursor-agent", "cursor-agent"),),
                strip_components=1,
            ),
            verify_argv=("cursor-agent", "status"),
            credential_env="CURSOR_API_KEY",
        ),
        # agy reads only GEMINI_API_KEY, and only when modelProvider is pinned to
        # gemini in its settings file: the variable alone has no effect.
        Harness(
            name="antigravity",
            secret_name="LIVE_ANTIGRAVITY_CREDENTIAL",
            binary="agy",
            source=PinnedArchive(
                version="1.5.5-6740358537805824",
                url="https://storage.googleapis.com/antigravity-public/antigravity-cli/1.5.5-6740358537805824/linux-x64/cli_linux_x64.tar.gz",
                sha256="bfe2c25edeadd98c2942417c9972ee0e1faa3f0afdc90711e84d5f3a633b5078",
                links=(("agy", "antigravity"),),
            ),
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
            # The official installer ends with an interactive `devin setup`,
            # which cannot complete on a runner; the credential file below is
            # what authenticates the CLI, so only the archive is installed.
            source=PinnedArchive(
                version="3000.12.43",
                url="https://static.devin.ai/cli/3000.12.43/devin-3000.12.43-x86_64-unknown-linux.tar.gz",
                sha256="6a19997b5fc2d6ba1a8c341d4e2b12f1b78cad5d415ee9c0ca413a8d52a99562",
                links=(("devin", "bin/devin"),),
            ),
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
        # A CLI absent after its own install ran is a failed setup, not a crash.
        print(f"live_harness_setup.py: {argv[0]} is not on PATH", file=sys.stderr)
        return 127


def _https_fetch(url: str, destination: Path) -> None:
    """Download ``url`` to ``destination``; the caller verifies the digest."""
    with (
        urllib.request.urlopen(url, timeout=300) as response,
        destination.open("wb") as handle,
    ):
        shutil.copyfileobj(response, handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stripped(archive: tarfile.TarFile, components: int):
    """Yield members with leading path components removed, as ``tar`` does."""
    for member in archive.getmembers():
        parts = PurePosixPath(member.name).parts
        if len(parts) <= components:
            continue
        member.name = str(PurePosixPath(*parts[components:]))
        if member.islnk():
            link = PurePosixPath(member.linkname).parts
            member.linkname = str(PurePosixPath(*link[components:]))
        yield member


def _link_binaries(
    home: Path, root: Path, links: Sequence[tuple[str, str]]
) -> str | None:
    """Expose each installed executable on PATH; return an error or None."""
    bin_dir = _resolved_within(home, _BIN_DIR)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, relative in links:
        target = root / relative
        if not target.exists():
            return f"{relative} is absent from the verified install of {name}"
        link = bin_dir / name
        link.unlink(missing_ok=True)
        link.symlink_to(target)
    return None


def _install_archive(source: PinnedArchive, home: Path, fetch: Fetcher) -> str | None:
    """Download, verify against the committed digest, then extract and link."""
    root = _resolved_within(home, _INSTALL_ROOT / "archives" / source.version)
    with tempfile.TemporaryDirectory() as staging:
        payload = Path(staging) / "payload.tar.gz"
        try:
            fetch(source.url, payload)
            actual = _sha256(payload)
        except OSError as error:
            return f"download failed for {source.url}: {error}"
        if actual != source.sha256:
            return (
                f"archive digest mismatch for {source.url}:"
                f" expected {source.sha256}, got {actual}"
            )
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True)
        try:
            with tarfile.open(payload, "r:gz") as archive:
                # The data filter rejects absolute paths, traversal, and links
                # that leave the destination.
                archive.extractall(
                    root,
                    members=_stripped(archive, source.strip_components),
                    filter="data",
                )
        except (tarfile.TarError, OSError) as error:
            shutil.rmtree(root, ignore_errors=True)
            return f"archive extraction failed for {source.url}: {error}"
    return _link_binaries(home, root, source.links)


def _install_npm(
    source: NpmLock, home: Path, runner: Runner, env: Mapping[str, str]
) -> str | None:
    """Install from the committed lockfile, outside the checkout."""
    root = _resolved_within(home, _INSTALL_ROOT / "npm" / source.project)
    try:
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True)
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(_LOCKFILES / source.project / name, root / name)
    except OSError as error:
        return f"pinned {source.project} lockfile is unavailable: {error}"
    # `npm ci` installs exactly the lockfile and fails on any integrity mismatch.
    argv = ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund")
    status = runner((*argv, "--prefix", str(root)), env)
    if status != 0:
        return f"npm ci exited {status} for the pinned {source.project} lockfile"
    return _link_binaries(home, root, source.links)


def _which(binary: str, env: Mapping[str, str]) -> str | None:
    return shutil.which(binary, path=env.get("PATH"))


def _fail(message: str) -> None:
    print(f"live_harness_setup.py: {message}", file=sys.stderr)


def _selected(argv: Sequence[str] | None) -> tuple[str, Harness | None]:
    parser = argparse.ArgumentParser(
        prog="live_harness_setup.py",
        description="Install, then authenticate, one native harness CLI for live parity.",
    )
    parser.add_argument(
        "phase",
        choices=("install", "authenticate"),
        help="install runs without the credential; authenticate runs after it",
    )
    parser.add_argument(
        "--harness",
        required=True,
        help=f"harness to provision ({', '.join(sorted(HARNESSES))})",
    )
    arguments = parser.parse_args(argv)
    harness = HARNESSES.get(arguments.harness)
    if harness is None:
        _fail(
            f"unknown harness {arguments.harness!r};"
            f" known harnesses: {', '.join(sorted(HARNESSES))}"
        )
    return arguments.phase, harness


def install(
    harness: Harness,
    environ: Mapping[str, str],
    *,
    runner: Runner,
    locator: Locator,
    fetch: Fetcher,
    host: tuple[str, str],
) -> int:
    """Install the pinned CLI. Return 0 only when its binary is on PATH."""
    if (environ.get(CREDENTIAL_VARIABLE) or "").strip():
        _fail(
            f"BLOCKED: {CREDENTIAL_VARIABLE} must not be set while installing"
            f" {harness.name}; run install in a step without the secret"
        )
        return 1
    if host != PINNED_PLATFORM:
        _fail(
            f"BLOCKED: {harness.name} is pinned for {'/'.join(PINNED_PLATFORM)},"
            f" not {'/'.join(host)}"
        )
        return 1
    home = Path(environ["HOME"])
    if isinstance(harness.source, NpmLock):
        error = _install_npm(harness.source, home, runner, environ)
    else:
        error = _install_archive(harness.source, home, fetch)
    if error is not None:
        _fail(f"BLOCKED: {error}")
        return 1
    if locator(harness.binary, environ) is None:
        _fail(f"BLOCKED: {harness.binary} is absent after installing {harness.name}")
        return 1
    print(f"live_harness_setup.py: {harness.name} installed from its pinned source")
    return 0


def authenticate(
    harness: Harness,
    environ: Mapping[str, str],
    *,
    runner: Runner,
    locator: Locator,
) -> int:
    """Provision the credential. Return 0 only when the CLI's probe accepts it."""
    credential = (environ.get(CREDENTIAL_VARIABLE) or "").strip()
    if not credential:
        _fail(
            f"BLOCKED: protected secret {harness.secret_name}"
            f" is required to authenticate {harness.name}"
        )
        return 1
    # The generic variable is dropped: the CLI gets only its own variable or file.
    base = {key: value for key, value in environ.items() if key != CREDENTIAL_VARIABLE}
    if locator(harness.binary, base) is None:
        _fail(f"BLOCKED: {harness.binary} is not installed; run install first")
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
    print(f"live_harness_setup.py: {harness.name} authenticated")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    locator: Locator | None = None,
    fetch: Fetcher | None = None,
    host: tuple[str, str] | None = None,
) -> int:
    """Run one phase. 2 = unknown harness; 1 = BLOCKED; 0 = the phase succeeded."""
    phase, harness = _selected(argv)
    if harness is None:
        return 2
    environ = os.environ if environ is None else environ
    runner = _subprocess_runner if runner is None else runner
    locator = _which if locator is None else locator
    if phase == "authenticate":
        return authenticate(harness, environ, runner=runner, locator=locator)
    return install(
        harness,
        environ,
        runner=runner,
        locator=locator,
        fetch=_https_fetch if fetch is None else fetch,
        host=(platform.system(), platform.machine()) if host is None else host,
    )


if __name__ == "__main__":
    raise SystemExit(main())
