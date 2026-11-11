"""Per-harness live-parity setup: pinned installs, credential isolation, real probes.

The protected live-parity job installs exactly one native CLI, then authenticates
it from exactly one protected secret and proves that with the harness's own
probe. These tests pin the properties a credential-handling helper cannot be
allowed to lose: nothing is installed from a mutable channel, an archive whose
digest differs from the committed one never runs, the install phase refuses to
share a step with the credential, the secret value never reaches stdout/stderr
or a world-readable file, a missing secret is an explicit BLOCKED error rather
than a silent skip, and a harness the registry does not know is refused before
any secret is read.
"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest

from tools import live_harness_setup
from tools.live_harness_setup import (
    CREDENTIAL_VARIABLE,
    HARNESSES,
    PINNED_PLATFORM,
    NpmLock,
    PinnedArchive,
    main,
    provision,
)

_SECRET = "cred-value-never-logged"
_NPM = sorted(n for n, h in HARNESSES.items() if isinstance(h.source, NpmLock))
_ARCHIVE = sorted(
    n for n, h in HARNESSES.items() if isinstance(h.source, PinnedArchive)
)
_LOCKFILES = Path(live_harness_setup.__file__).resolve().parent / "live_harness"


class _Runner:
    """Records dispatched argv plus the environment each command received."""

    def __init__(self, failures: dict[str, int] | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
        self._failures = failures or {}

    def __call__(self, argv, env):
        self.calls.append((tuple(argv), dict(env)))
        if argv[:2] == ("npm", "ci"):
            # Stand in for npm: create the executables the lockfile would.
            root = Path(argv[argv.index("--prefix") + 1])
            (root / "node_modules/.bin").mkdir(parents=True)
            for name in ("claude", "codex"):
                (root / "node_modules/.bin" / name).write_text("#!/bin/sh\n")
        return self._failures.get(argv[0], 0)

    @property
    def dispatched(self) -> list[tuple[str, ...]]:
        return [argv for argv, _ in self.calls]


def _tarball(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _fetcher(payload: bytes, seen: list[str] | None = None):
    def fetch(url: str, destination: Path) -> None:
        if seen is not None:
            seen.append(url)
        destination.write_bytes(payload)

    return fetch


def _environment(tmp_path: Path, secret: str | None) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    github_env = tmp_path / "github.env"
    github_env.touch()
    environment = {"HOME": str(home), "GITHUB_ENV": str(github_env)}
    if secret is not None:
        environment[CREDENTIAL_VARIABLE] = secret
    return environment


def _install(harness: str, tmp_path: Path, *, secret=None, fetch=None, host=None):
    runner = _Runner()
    environment = _environment(tmp_path, secret)
    status = main(
        ["install", "--harness", harness],
        environ=environment,
        runner=runner,
        locator=lambda binary, env: (
            str(found)
            if (found := Path(env["HOME"]) / ".local/bin" / binary).exists()
            else None
        ),
        fetch=fetch or _fetcher(b"not the pinned archive"),
        host=host or PINNED_PLATFORM,
    )
    return status, runner, tmp_path / "home"


def _authenticate(
    harness: str, tmp_path: Path, *, secret=_SECRET, runner=None, installed=True
):
    runner = runner if runner is not None else _Runner()
    status = main(
        ["authenticate", "--harness", harness],
        environ=_environment(tmp_path, secret),
        runner=runner,
        locator=lambda binary, _env: f"/usr/local/bin/{binary}" if installed else None,
    )
    return status, runner, tmp_path / "home", tmp_path / "github.env"


def _pin_fake_archive(monkeypatch, harness: str, members: dict[str, bytes]) -> bytes:
    """Repoint a harness at a fake archive whose digest is the committed one."""
    payload = _tarball(members)
    source = replace(
        HARNESSES[harness].source, sha256=hashlib.sha256(payload).hexdigest()
    )
    monkeypatch.setitem(HARNESSES, harness, replace(HARNESSES[harness], source=source))
    return payload


# --- what may be installed -------------------------------------------------


@pytest.mark.parametrize("harness", _NPM)
def test_npm_harnesses_are_pinned_by_a_committed_lockfile(harness: str) -> None:
    project = _LOCKFILES / HARNESSES[harness].source.project
    package = json.loads((project / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "package-lock.json").read_text(encoding="utf-8"))

    for version in package["dependencies"].values():
        assert version[0].isdigit(), f"dependency must be an exact version: {version}"
    fetched = [entry for entry in lock["packages"].values() if "resolved" in entry]
    assert fetched
    for entry in fetched:
        assert entry["integrity"].startswith("sha512-"), entry["resolved"]
        assert entry["resolved"].startswith("https://registry.npmjs.org/")


@pytest.mark.parametrize("harness", _ARCHIVE)
def test_archive_harnesses_pin_a_versioned_url_and_a_digest(harness: str) -> None:
    source = HARNESSES[harness].source

    assert source.url.startswith("https://")
    assert source.version in source.url
    assert len(source.sha256) == 64


def test_an_unversioned_or_undigested_archive_cannot_be_registered() -> None:
    with pytest.raises(ValueError):
        PinnedArchive("1.0", "https://example.test/latest/cli.tar.gz", "a" * 64, ())
    with pytest.raises(ValueError):
        PinnedArchive("1.0", "https://example.test/1.0/cli.tar.gz", "latest", ())
    with pytest.raises(ValueError):
        PinnedArchive("1.0", "http://example.test/1.0/cli.tar.gz", "a" * 64, ())


def test_no_upstream_installer_script_is_ever_executed() -> None:
    source = Path(live_harness_setup.__file__).read_text(encoding="utf-8")

    assert "curl" not in source
    assert '"install", "-g"' not in source
    assert "install.sh" not in source


# --- install phase ---------------------------------------------------------


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_install_refuses_to_share_a_step_with_the_credential(
    harness: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    status, runner, home = _install(
        harness, tmp_path, secret=_SECRET, fetch=_fetcher(b"", seen)
    )

    assert status == 1
    assert runner.dispatched == [] and seen == []
    assert not (home / ".local").exists()
    captured = capsys.readouterr()
    assert "BLOCKED" in captured.err and _SECRET not in captured.err


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_install_is_blocked_on_a_platform_without_a_pin(
    harness: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, runner, _ = _install(harness, tmp_path, host=("Darwin", "arm64"))

    assert status == 1
    assert runner.dispatched == []
    assert "BLOCKED" in capsys.readouterr().err


@pytest.mark.parametrize("harness", _NPM)
def test_npm_install_runs_only_npm_ci_on_the_committed_lockfile(
    harness: str, tmp_path: Path
) -> None:
    status, runner, home = _install(harness, tmp_path)

    assert status == 0
    (argv,) = runner.dispatched
    assert argv[:3] == ("npm", "ci", "--ignore-scripts")
    root = Path(argv[argv.index("--prefix") + 1])
    project = _LOCKFILES / HARNESSES[harness].source.project
    for name in ("package.json", "package-lock.json"):
        assert (root / name).read_bytes() == (project / name).read_bytes()
    assert (home / ".local/bin" / HARNESSES[harness].binary).is_symlink()


def test_a_failing_npm_ci_is_blocked(tmp_path: Path) -> None:
    runner = _Runner(failures={"npm": 1})
    status = main(
        ["install", "--harness", "claude"],
        environ=_environment(tmp_path, None),
        runner=runner,
        locator=lambda *_: None,
        host=PINNED_PLATFORM,
    )

    assert status == 1
    assert not (tmp_path / "home/.local/bin/claude").exists()


def test_a_verified_archive_is_extracted_and_linked(tmp_path, monkeypatch) -> None:
    payload = _pin_fake_archive(
        monkeypatch, "cursor", {"dist-package/cursor-agent": b"#!/bin/sh\n"}
    )
    seen: list[str] = []

    status, runner, home = _install("cursor", tmp_path, fetch=_fetcher(payload, seen))

    assert status == 0
    assert runner.dispatched == []
    assert seen == [HARNESSES["cursor"].source.url]
    linked = home / ".local/bin/cursor-agent"
    assert linked.is_symlink() and linked.read_text() == "#!/bin/sh\n"


@pytest.mark.parametrize("harness", _ARCHIVE)
def test_an_archive_with_the_wrong_digest_is_never_extracted(
    harness: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = HARNESSES[harness].source.links[0][1]
    tampered = _tarball({binary: b"#!/bin/sh\necho compromised\n"})

    status, _, home = _install(harness, tmp_path, fetch=_fetcher(tampered))

    assert status == 1
    assert not (home / ".local").exists()
    assert "digest mismatch" in capsys.readouterr().err


def test_an_archive_escaping_its_directory_is_blocked(tmp_path, monkeypatch) -> None:
    payload = _pin_fake_archive(
        monkeypatch, "devin", {"../../escaped": b"x", "bin/devin": b"x"}
    )

    status, _, home = _install("devin", tmp_path, fetch=_fetcher(payload))

    assert status == 1
    assert not (home / ".local/bin/devin").exists()
    assert not list(tmp_path.rglob("escaped"))


def test_a_failed_download_is_blocked(tmp_path: Path, capsys) -> None:
    def fetch(url: str, destination: Path) -> None:
        raise OSError("connection reset")

    status, _, _ = _install("devin", tmp_path, fetch=fetch)

    assert status == 1
    assert "BLOCKED" in capsys.readouterr().err


# --- authenticate phase ----------------------------------------------------


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_authenticate_only_runs_the_probe(harness: str, tmp_path: Path) -> None:
    status, runner, _, _ = _authenticate(harness, tmp_path)

    assert status == 0
    assert runner.dispatched == [tuple(HARNESSES[harness].verify_argv)]


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_the_probe_receives_only_the_harness_own_credential(
    harness: str, tmp_path: Path
) -> None:
    _, runner, _, _ = _authenticate(harness, tmp_path)

    (_, probe_env) = runner.calls[0]
    assert CREDENTIAL_VARIABLE not in probe_env
    carriers = [key for key, value in probe_env.items() if _SECRET in value]
    expected = HARNESSES[harness].credential_env
    assert carriers == ([] if expected is None else [expected])


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_missing_secret_is_an_explicit_blocked_error(
    harness: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, runner, _, _ = _authenticate(harness, tmp_path, secret=None)

    assert status == 1
    assert runner.dispatched == []
    captured = capsys.readouterr()
    assert "BLOCKED" in captured.err
    assert HARNESSES[harness].secret_name in captured.err


def test_authenticating_a_cli_that_was_never_installed_is_blocked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, runner, _, github_env = _authenticate("claude", tmp_path, installed=False)

    assert status == 1
    assert runner.dispatched == []
    assert github_env.read_text(encoding="utf-8") == ""
    assert "BLOCKED" in capsys.readouterr().err


@pytest.mark.parametrize("phase", ("install", "authenticate"))
def test_unknown_harness_is_refused_before_any_secret_is_read(
    phase: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Runner()
    status = main(
        [phase, "--harness", "not-a-harness"],
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
    _authenticate(harness, tmp_path)

    captured = capsys.readouterr()
    assert _SECRET not in captured.out
    assert _SECRET not in captured.err


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_credential_files_are_owner_only(harness: str, tmp_path: Path) -> None:
    _, _, home, _ = _authenticate(harness, tmp_path)

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
    _, _, home, github_env = _authenticate("devin", tmp_path)

    assert (home / HARNESSES["devin"].credential_path).exists()
    assert _SECRET not in github_env.read_text(encoding="utf-8")


def test_antigravity_selects_the_gemini_provider_it_requires(tmp_path: Path) -> None:
    _, _, home, github_env = _authenticate("antigravity", tmp_path)

    settings = json.loads(
        (home / ".gemini/antigravity-cli/settings.json").read_text(encoding="utf-8")
    )
    assert settings["modelProvider"] == "gemini"
    assert f"GEMINI_API_KEY={_SECRET}" in github_env.read_text(encoding="utf-8")


@pytest.mark.parametrize("harness", sorted(HARNESSES))
def test_environment_authenticated_harnesses_export_exactly_one_variable(
    harness: str, tmp_path: Path
) -> None:
    _, _, _, github_env = _authenticate(harness, tmp_path)

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

    status, runner, _, _ = _authenticate("claude", tmp_path, runner=runner)

    assert status == 1
    assert len(runner.dispatched) == 1


def test_provision_refuses_a_path_escaping_the_home_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        provision(
            HARNESSES["devin"],
            _SECRET,
            home=tmp_path / "home",
            github_env=tmp_path / "env",
            credential_path_override=Path("../escaped/credentials.toml"),
        )
