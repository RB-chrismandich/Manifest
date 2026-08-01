"""T5.1 (spec 674) — dropping one domain's claim from an apm lockfile.

Driven by subprocess rather than imported like its sibling: this script does its
work at module top level and calls sys.exit, so importing it runs it.

The NEGATIVE case carries the weight. apm_ownership_report.sh reads this
lockfile to decide who owns a domain, so a dropper that clears a domain nobody
named hands ownership of that domain back to nothing — and still passes every
"did it drop?" assertion. The unreadable-lockfile cases are guards on the read:
each must exit 1 rather than leak a traceback, because the caller
(apm_ungate_domain.sh) branches on the exit code and prints its own message.
"""

import pathlib
import subprocess
import sys

import yaml

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs/claude/scripts/apm_drop_domain_claim.py"
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _lockfile(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "apm.lock.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "dependencies": [
                    {
                        "name": "skills-dep",
                        "deployed_files": [".claude/skills/a", ".claude/skills/b"],
                        "deployed_file_hashes": {".claude/skills/a": "h1"},
                    },
                    {
                        "name": "agents-dep",
                        "deployed_files": [".claude/agents/keep"],
                        "deployed_file_hashes": {".claude/agents/keep": "h2"},
                    },
                ],
                "deployments": [
                    {"value": ".claude/skills/a"},
                    {"value": ".claude/agents/keep"},
                ],
            }
        )
    )
    return path


def test_named_domain_claim_is_dropped(tmp_path):
    path = _lockfile(tmp_path)
    assert _run(str(path), "skills").returncode == 0
    data = yaml.safe_load(path.read_text())
    assert ".claude/skills" not in yaml.safe_dump(data)


def test_an_unnamed_domain_claim_survives(tmp_path):
    """Dropping `skills` must not disturb the `agents` claim."""
    path = _lockfile(tmp_path)
    assert _run(str(path), "skills").returncode == 0
    data = yaml.safe_load(path.read_text())
    names = [d["name"] for d in data["dependencies"]]
    assert names == ["agents-dep"], "the husk is dropped, the live claim is kept"
    assert data["dependencies"][0]["deployed_files"] == [".claude/agents/keep"]
    assert data["deployments"] == [{"value": ".claude/agents/keep"}]


def test_missing_lockfile_exits_one(tmp_path):
    result = _run(str(tmp_path / "nope.yaml"), "skills")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_malformed_yaml_exits_one(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("a: [unclosed\n")
    result = _run(str(path), "skills")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_non_utf8_lockfile_exits_one_without_a_traceback(tmp_path):
    """UnicodeDecodeError is a ValueError, so an OSError-only guard misses it."""
    path = tmp_path / "binary.yaml"
    path.write_bytes(b"\xff\xfe\x00\x01binary")
    result = _run(str(path), "skills")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_help_exits_zero():
    result = _run("--help")
    assert result.returncode == 0
    assert "Usage:" in result.stdout


def test_missing_arguments_exit_two():
    assert _run("only-one-arg").returncode == 2
