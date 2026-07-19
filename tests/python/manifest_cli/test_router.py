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


def test_help_does_not_list_retired_cddl():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "cddl" not in result.output
