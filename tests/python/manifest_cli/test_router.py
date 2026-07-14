import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

from click.testing import CliRunner

from manifest_cli import cli


def test_help_lists_parallel_agent():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "parallel-agent" in result.output


def test_cddl_delegates_argv(monkeypatch):
    captured = {}

    def fake_main(argv=None):
        captured["argv"] = list(argv or [])
        return 0

    monkeypatch.setattr("cddl.cli.main", fake_main)
    result = CliRunner().invoke(cli, ["cddl", "status"])
    assert result.exit_code == 0
    assert captured["argv"] == ["status"]


def test_cddl_preserves_exit_code(monkeypatch):
    monkeypatch.setattr("cddl.cli.main", lambda argv=None: 7)
    result = CliRunner().invoke(cli, ["cddl", "run"])
    assert result.exit_code == 7
