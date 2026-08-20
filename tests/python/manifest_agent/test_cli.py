"""Control-plane CLI and stable lifecycle report tests."""

from __future__ import annotations

import json

from click.testing import CliRunner

import manifest_agent.cli as cli_module
from manifest_agent.models import HarnessResult, OwnedEntry, ResultState
from manifest_agent.service import ServiceReport


def test_cli_lists_exact_control_plane_commands():
    result = CliRunner().invoke(cli_module.cli, ["--help"])

    assert result.exit_code == 0
    assert all(
        name in result.output
        for name in ("install", "migrate", "reconcile", "update", "uninstall")
    )
    assert "parallel-agent" not in result.output


def test_lifecycle_commands_expose_exact_common_options():
    runner = CliRunner()

    for command in ("install", "migrate", "reconcile", "update", "uninstall"):
        result = runner.invoke(cli_module.cli, [command, "--help"])
        assert result.exit_code == 0
        assert all(
            option in result.output
            for option in (
                "--harness",
                "--source",
                "--release",
                "--with",
                "--non-interactive",
                "--json",
            )
        )


def test_source_and_release_are_mutually_exclusive(tmp_path):
    result = CliRunner().invoke(
        cli_module.cli,
        ["install", "--source", str(tmp_path), "--release", "1.0.0"],
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_install_forwards_repeated_harness_and_optional_selection(monkeypatch):
    recorded = {}
    report = ServiceReport("install", ResultState.READY, {})

    class FakeService:
        def install(self):
            return report

    def fake_service(**options):
        recorded.update(options)
        return FakeService()

    monkeypatch.setattr(cli_module, "_service", fake_service)

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "install",
            "--harness",
            "all",
            "--with",
            "github",
            "--with",
            "sentry",
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert recorded["harnesses"] == ("all",)
    assert recorded["selected_optional"] == ("github", "sentry")
    assert recorded["non_interactive"] is True


def test_json_report_is_stable_and_machine_readable(monkeypatch):
    report = ServiceReport(
        "reconcile",
        ResultState.DEGRADED,
        {
            "claude": HarnessResult(
                "claude",
                ResultState.DEGRADED,
                ("manifest-workspace",),
                {"mcp:context7": "degraded"},
                errors=("missing default capability",),
            )
        },
        notes=("codex: CLI not present",),
    )

    class FakeService:
        def reconcile(self, apply=False):
            assert apply is False
            return report

    monkeypatch.setattr(cli_module, "_service", lambda **options: FakeService())

    result = CliRunner().invoke(cli_module.cli, ["reconcile", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == report.to_dict()
    assert (
        result.output
        == json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    )


def test_blocked_json_report_has_nonzero_exit_without_extra_output(monkeypatch):
    report = ServiceReport("uninstall", ResultState.BLOCKED, {})

    class FakeService:
        def uninstall(self):
            return report

    monkeypatch.setattr(cli_module, "_service", lambda **options: FakeService())

    result = CliRunner().invoke(cli_module.cli, ["uninstall", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.output) == report.to_dict()


def test_report_redacts_credential_values_and_keys():
    report = ServiceReport(
        "install",
        ResultState.BLOCKED,
        {
            "claude": HarnessResult(
                "claude",
                ResultState.BLOCKED,
                ("plugin --token super-secret",),
                {"api_token": "secret=hidden-value"},
                errors=("failed --authorization bearer-value",),
                owned_entries=(
                    OwnedEntry(
                        "plugin",
                        "manifest",
                        "manifest",
                        "Authorization: Bearer owned-secret",
                    ),
                ),
            )
        },
    )

    rendered = json.dumps(report.to_dict(), sort_keys=True)

    assert "super-secret" not in rendered
    assert "hidden-value" not in rendered
    assert "bearer-value" not in rendered
    assert "owned-secret" not in repr(report)
    assert "api_token" not in rendered
    assert "[REDACTED]" in rendered


def test_migrate_runs_the_lifecycle_service(monkeypatch):
    report = ServiceReport("migrate", ResultState.READY, {})

    class FakeService:
        def migrate(self):
            return report

    monkeypatch.setattr(cli_module, "_service", lambda **options: FakeService())

    result = CliRunner().invoke(cli_module.cli, ["migrate"])

    assert result.exit_code == 0
    assert "migrate: READY" in result.output


def test_skill_run_missing_provider_is_a_stable_usage_error(tmp_path, monkeypatch):
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: demo\n---\nDo the work.\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "skill-run",
            str(skill),
            "--harness",
            "devin",
            "--non-interactive",
        ],
        input="private task",
    )

    assert result.exit_code == 2
    assert "provider launch failed before execution" in result.output
    assert "Traceback" not in result.output


def test_update_is_an_alias_for_the_reconcile_repair_path(monkeypatch):
    """`update` must apply, not merely inspect.

    The capability already existed as `reconcile --apply`; the alias exists so
    upgrading is discoverable without knowing that a command named for drift
    inspection is also the upgrade path. If it ever stopped passing apply=True
    it would silently become a no-op that reports success.
    """
    seen = {}

    class FakeService:
        def reconcile(self, apply=False):
            seen["apply"] = apply
            return ServiceReport("reconcile", ResultState.READY, {})

    monkeypatch.setattr(cli_module, "_service", lambda **options: FakeService())

    result = CliRunner().invoke(cli_module.cli, ["update"])

    assert result.exit_code == 0
    assert seen["apply"] is True
