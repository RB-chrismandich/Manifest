"""The commandments checker's delivery surface: the CLI and the save hook.

Separated from the rule tests because these assert a different kind of thing —
not "is this document compliant" but "does the tool stay out of the user's way".
Everything here is about exit codes, output channels, and failure modes, and
every one of them must be non-blocking.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugins" / "manifest-docker"
SCRIPTS = PLUGIN / "scripts"
CHECKER = SCRIPTS / "compose_check.py"
TEMPLATE = (
    PLUGIN
    / "skills"
    / "docker-compose-commandments"
    / "references"
    / "compose-template.yaml"
)
HOOK = PLUGIN / "hooks" / "compose_commandments_hook.py"


# --------------------------------------------------------------------------- #
# CLI contract
# --------------------------------------------------------------------------- #


def run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(CHECKER), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_exits_zero_and_stays_within_fifteen_lines():
    """Repo convention: --help answers before any config or state lookup."""
    result = run_checker("--help")
    assert result.returncode == 0
    assert len(result.stdout.strip().splitlines()) <= 15


def test_advisory_by_default_and_strict_on_request(tmp_path):
    path = tmp_path / "docker-compose.yaml"
    path.write_text("services:\n  a:\n    image: nginx:latest\n", encoding="utf-8")
    assert run_checker(str(path)).returncode == 0, (
        "default mode must never fail a build"
    )
    assert run_checker(str(path), "--strict").returncode == 1


def test_strict_exits_zero_when_clean(tmp_path):
    assert run_checker(str(TEMPLATE), "--strict").returncode == 0


def test_json_output_is_parseable(tmp_path):
    path = tmp_path / "docker-compose.yaml"
    path.write_text("services:\n  a:\n    image: nginx:latest\n", encoding="utf-8")
    payload = json.loads(run_checker(str(path), "--json").stdout)
    assert payload["total"] > 0
    assert {"rule_id", "severity", "line", "message"} <= set(
        payload["findings"][str(path)][0]
    )


def test_malformed_yaml_is_reported_without_aborting_the_sweep(tmp_path):
    (tmp_path / "docker-compose.yaml").write_text(
        "services: [unclosed\n", encoding="utf-8"
    )
    (tmp_path / "compose.yaml").write_text(
        "services:\n  a:\n    image: nginx:latest\n", encoding="utf-8"
    )
    result = run_checker(str(tmp_path), "--strict")
    assert "skipped" in result.stderr
    assert result.returncode == 1, "the readable file must still be checked"


# --------------------------------------------------------------------------- #
# Hook adapter — advisory under every failure mode
# --------------------------------------------------------------------------- #


def run_hook(payload: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "",
        "{}",
        '{"tool_input": {}}',
        '{"tool_input": {"file_path": "/nonexistent/docker-compose.yaml"}}',
        "[1, 2, 3]",
    ],
    ids=[
        "garbage",
        "empty",
        "no-tool-input",
        "no-path",
        "missing-file",
        "not-a-mapping",
    ],
)
def test_hook_exits_zero_on_every_malformed_payload(payload):
    """A PostToolUse hook that can fail is a hook that can block an edit."""
    assert run_hook(payload).returncode == 0


def test_hook_is_silent_on_files_it_does_not_own(tmp_path):
    other = tmp_path / "values.yaml"
    other.write_text("services:\n  a:\n    image: nginx:latest\n", encoding="utf-8")
    result = run_hook(json.dumps({"tool_input": {"file_path": str(other)}}))
    assert result.returncode == 0
    assert result.stdout == "" and result.stderr == ""


def test_hook_reports_on_stderr_and_still_exits_zero(tmp_path):
    path = tmp_path / "docker-compose.yaml"
    path.write_text("services:\n  a:\n    image: nginx:latest\n", encoding="utf-8")
    result = run_hook(json.dumps({"tool_input": {"file_path": str(path)}}))
    assert result.returncode == 0
    assert "DC-001" in result.stderr
    assert result.stdout == "", (
        "findings belong on stderr; stdout is the tool's channel"
    )


def test_hook_stays_silent_when_its_own_checker_is_broken(tmp_path):
    """The guard the malformed-payload cases never reach.

    Every bad-payload test above returns before the try block, so none of them
    exercise the handler wrapping the import and the subprocess. This one does:
    a plugin tree whose checker cannot even be imported. A broken checker must
    still cost the user nothing.
    """
    fake = tmp_path / "plugin"
    (fake / "hooks").mkdir(parents=True)
    (fake / "scripts").mkdir()
    (fake / "config").mkdir()
    (fake / "hooks" / HOOK.name).write_bytes(HOOK.read_bytes())
    (fake / "scripts" / "compose_check.py").write_text("def (\n", encoding="utf-8")
    (fake / "config" / "compose_commandments.yml").write_text(
        "filenames: []\n", encoding="utf-8"
    )

    target = tmp_path / "docker-compose.yaml"
    target.write_text("services:\n  a:\n    image: nginx:latest\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-B", str(fake / "hooks" / HOOK.name)],
        input=json.dumps({"tool_input": {"file_path": str(target)}}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == "", "a broken checker must not spray tracebacks at the user"


def test_hook_writes_no_bytecode_into_an_installed_plugin(tmp_path):
    """Importing the checker to read the filename registry once littered
    __pycache__/ through the plugin tree and broke a repo naming gate."""
    for stale in PLUGIN.rglob("__pycache__"):
        for item in stale.iterdir():
            item.unlink()
        stale.rmdir()
    path = tmp_path / "docker-compose.yaml"
    path.write_text("services:\n  a:\n    image: nginx:latest\n", encoding="utf-8")
    run_hook(json.dumps({"tool_input": {"file_path": str(path)}}))
    assert list(PLUGIN.rglob("__pycache__")) == []


def _many_findings(tmp_path: Path) -> Path:
    """A compose file with far more findings than any cap would show."""
    services = "".join(f"  s{n}:\n    image: nginx:latest\n" for n in range(10))
    path = tmp_path / "docker-compose.yaml"
    path.write_text(f"services:\n{services}", encoding="utf-8")
    return path


def test_limit_caps_the_printed_findings(tmp_path):
    path = _many_findings(tmp_path)
    uncapped = run_checker(str(path)).stdout
    capped = run_checker(str(path), "--limit", "5").stdout
    assert len(capped.splitlines()) < len(uncapped.splitlines())


def test_a_truncated_report_never_reads_as_complete(tmp_path):
    """The failure mode a cap introduces: output that looks like the whole story.

    The total and the omitted count must both survive truncation, or a user
    fixes the twelve findings they were shown and believes the file is clean.
    """
    path = _many_findings(tmp_path)
    total = len(
        json.loads(run_checker(str(path), "--json").stdout)["findings"][str(path)]
    )
    capped = run_checker(str(path), "--limit", "5").stdout
    assert f"{total} finding(s)" in capped, "the true total must survive the cap"
    assert f"{total - 5} more not shown" in capped, "the omitted count must be stated"


def test_no_limit_prints_everything(tmp_path):
    path = _many_findings(tmp_path)
    assert "more not shown" not in run_checker(str(path)).stdout


def test_the_hook_caps_its_own_output(tmp_path):
    """The hook audits the whole file on every edit, so it must cap; a 26-service
    stack otherwise emits 134 findings into context for a one-line change."""
    path = _many_findings(tmp_path)
    stderr = run_hook(json.dumps({"tool_input": {"file_path": str(path)}})).stderr
    assert "more not shown" in stderr
    assert len(stderr.splitlines()) < 40
