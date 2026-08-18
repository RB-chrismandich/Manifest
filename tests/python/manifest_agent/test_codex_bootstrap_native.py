"""Opt-in native Codex acceptance coverage for the reported migration state."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_NATIVE = os.environ.get("MANIFEST_RUN_NATIVE_CODEX") == "1"
NATIVE_HOME = os.environ.get("MANIFEST_NATIVE_CODEX_HOME")

pytestmark = [
    pytest.mark.native,
    pytest.mark.skipif(
        not RUN_NATIVE or not NATIVE_HOME,
        reason=(
            "set MANIFEST_RUN_NATIVE_CODEX=1 and MANIFEST_NATIVE_CODEX_HOME to "
            "an isolated, authenticated home seeded with the nine-plugin state"
        ),
    ),
]


@dataclass(frozen=True)
class NativeConvergence:
    """Artifacts captured across two successful native bootstrap passes."""

    home: Path
    first_report: dict
    second_report: dict
    probe_log: Path
    first_snapshot: dict[str, tuple]
    second_snapshot: dict[str, tuple]


def _run(
    home: Path,
    *argv: str,
    input_text: str | None = None,
    extra_env: dict[str, str] | None = None,
):
    environment = dict(os.environ)
    environment["HOME"] = str(home)
    environment["XDG_STATE_HOME"] = str(home / ".local/state")
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        argv,
        cwd=REPO_ROOT,
        env=environment,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _plugins(home: Path) -> list[dict]:
    result = _run(home, "codex", "plugin", "list", "--json")
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    return document["plugins"] if isinstance(document, dict) else document


def _prompt_input(home: Path) -> tuple[str, str]:
    result = _run(home, "codex", "debug", "prompt-input")
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    prompt = "\n".join(
        block["text"]
        for message in document
        for block in message.get("content", [])
        if isinstance(block.get("text"), str)
    )
    return prompt, result.stderr


def _snapshot(paths: list[Path]) -> dict[str, tuple]:
    snapshot = {}
    for root in paths:
        candidates = [root]
        if root.is_dir() and not root.is_symlink():
            candidates.extend(sorted(root.rglob("*")))
        for path in candidates:
            if not path.exists() and not path.is_symlink():
                continue
            info = path.lstat()
            key = str(path)
            if path.is_symlink():
                snapshot[key] = (
                    "link",
                    info.st_mode,
                    info.st_mtime_ns,
                    str(path.readlink()),
                )
            elif path.is_file():
                snapshot[key] = (
                    "file",
                    info.st_mode,
                    info.st_mtime_ns,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            else:
                snapshot[key] = ("dir", info.st_mode, info.st_mtime_ns)
    return snapshot


def _validated_seed_home() -> Path:
    assert NATIVE_HOME is not None
    home = Path(NATIVE_HOME).resolve()
    assert home != Path.home().resolve(), "native test must never target the real HOME"
    before = _plugins(home)
    manifest_before = {
        row["pluginId"]
        for row in before
        if row.get("pluginId", "").endswith("@manifest")
    }
    assert len(manifest_before) == 9
    assert "manifest-delegate@manifest" not in manifest_before
    upstream = next(
        row for row in before if row.get("pluginId") == "i-have-adhd@i-have-adhd"
    )
    assert upstream.get("enabled") is not False
    assert (home / ".codex/skills").is_symlink()
    return home


def _native_wrapper_environment(home: Path) -> tuple[dict[str, str], Path]:
    real_codex = shutil.which("codex")
    assert real_codex is not None
    wrapper_bin = home / ".manifest-native-test/bin"
    wrapper_bin.mkdir(parents=True, exist_ok=True)
    probe_log = home / ".manifest-native-test/probe.log"
    codex_wrapper = wrapper_bin / "codex"
    codex_wrapper.write_text(f'#!/bin/sh\nexec {real_codex!r} "$@"\n', encoding="utf-8")
    codex_wrapper.chmod(0o755)
    python_wrapper = wrapper_bin / "python3"
    python_wrapper.write_text(
        "#!/bin/sh\n"
        'case "${1:-}" in\n'
        "  */manifest-i-have-adhd/hooks/always_on.py)\n"
        f"    {sys.executable!r} - {str(home / '.codex/config.toml')!r} "
        f"{str(home / '.codex/skills')!r} {str(probe_log)!r} <<'PY'\n"
        "import pathlib, sys, tomllib\n"
        "config, skills, log = map(pathlib.Path, sys.argv[1:])\n"
        "document = tomllib.loads(config.read_text())\n"
        "upstream = document.get('plugins', {}).get('i-have-adhd@i-have-adhd', {})\n"
        "assert upstream.get('enabled') is not False\n"
        "assert skills.is_symlink()\n"
        "log.write_text('probe-before-mutation\\n')\n"
        "PY\n"
        "    ;;\n"
        "esac\n"
        f'exec {sys.executable!r} "$@"\n',
        encoding="utf-8",
    )
    python_wrapper.chmod(0o755)
    return {"PATH": f"{wrapper_bin}:{os.environ['PATH']}"}, probe_log


def _bootstrap_command() -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "manifest",
        "bootstrap-sync",
        "--source",
        str(REPO_ROOT),
        "--harness",
        "codex",
        "--non-interactive",
        "--json",
    )


def _run_ready_bootstrap(
    home: Path, command: tuple[str, ...], wrapper_env: dict[str, str]
) -> dict:
    result = _run(home, *command, extra_env=wrapper_env)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["state"] == "READY"
    return report


def _tracked_native_paths(home: Path) -> list[Path]:
    return [home / ".codex/config.toml", home / ".codex/skills"] + [
        Path(row["source"]["path"])
        for row in _plugins(home)
        if row.get("pluginId", "").endswith("@manifest")
        and isinstance(row.get("source"), dict)
        and isinstance(row["source"].get("path"), str)
    ]


@pytest.fixture(scope="module")
def converged_home() -> NativeConvergence:
    """Converge the isolated native home twice and retain both snapshots."""
    home = _validated_seed_home()
    wrapper_env, probe_log = _native_wrapper_environment(home)
    command = _bootstrap_command()
    first_report = _run_ready_bootstrap(home, command, wrapper_env)
    tracked = _tracked_native_paths(home)
    first_snapshot = _snapshot(tracked)
    second_report = _run_ready_bootstrap(home, command, wrapper_env)
    second_snapshot = _snapshot(tracked)
    return NativeConvergence(
        home,
        first_report,
        second_report,
        probe_log,
        first_snapshot,
        second_snapshot,
    )


def test_native_nine_installed_two_missing_converges_and_is_idempotent(
    converged_home: NativeConvergence,
) -> None:
    after = _plugins(converged_home.home)
    manifest_ids = {
        row["pluginId"]
        for row in after
        if row.get("pluginId", "").endswith("@manifest")
    }
    assert "manifest-delegate@manifest" in manifest_ids
    assert converged_home.first_report["state"] == "READY"
    assert converged_home.second_report["state"] == "READY"
    assert converged_home.second_snapshot == converged_home.first_snapshot


def test_native_hook_probe_precedes_upstream_disable_and_system_only_cutover(
    converged_home: NativeConvergence,
) -> None:
    home = converged_home.home
    assert converged_home.probe_log.read_text(encoding="utf-8") == (
        "probe-before-mutation\n"
    )
    rows = _plugins(home)
    upstream = next(
        row for row in rows if row.get("pluginId") == "i-have-adhd@i-have-adhd"
    )
    mirrored = next(
        row for row in rows if row.get("pluginId") == "manifest-i-have-adhd@manifest"
    )
    assert upstream.get("installed") is not False
    assert upstream.get("enabled") is False
    launcher = Path(mirrored["source"]["path"]) / "hooks/always_on.py"
    probe = _run(
        home,
        sys.executable,
        str(launcher),
        input_text='{"hook_event_name":"SessionStart"}',
    )
    assert probe.returncode == 0
    assert probe.stdout.startswith("Manifest ADHD guidance v0.1.0\n")
    skills = home / ".codex/skills"
    assert not skills.is_symlink()
    assert {entry.name for entry in skills.iterdir()} <= {".system"}


def test_native_fresh_session_has_no_context_or_hook_warning(
    converged_home: NativeConvergence,
) -> None:
    session = _run(
        converged_home.home,
        "codex",
        "exec",
        "--skip-git-repo-check",
        "Reply only READY",
    )
    combined = (session.stdout + "\n" + session.stderr).lower()
    assert "skills context budget" not in combined
    assert "hook failure" not in combined
    assert "hook failed" not in combined


def test_native_prompt_input_keeps_only_manifest_implicit_entry_points(
    converged_home: NativeConvergence,
) -> None:
    prompt, stderr = _prompt_input(converged_home.home)
    combined = (prompt + "\n" + stderr).lower()

    assert "skills context budget" not in combined
    for qualified_name in (
        "manifest-code-quality:antipattern-detect",
        "manifest-security:code-audit",
        "manifest-workspace:help",
    ):
        assert f"- {qualified_name}:" in prompt
    assert "- manifest-code-quality:project-verify:" not in prompt
