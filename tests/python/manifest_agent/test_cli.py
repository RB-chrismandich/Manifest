"""Control-plane-only CLI contract."""

from click.testing import CliRunner

from manifest_agent.cli import cli


def test_cli_lists_only_control_plane_commands():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert all(
        name in result.output
        for name in ("install", "migrate", "reconcile", "uninstall")
    )
    assert "parallel-agent" not in result.output


def test_control_plane_commands_remain_explicitly_unimplemented():
    runner = CliRunner()

    for command in ("install", "migrate", "reconcile", "uninstall"):
        result = runner.invoke(cli, [command])
        assert result.exit_code != 0
        assert "not implemented" in result.output
