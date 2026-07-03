"""Migration shim: legacy browser-use YAML → smoke catalog agent steps.

Every migrated entry must be tier Full (agent steps are forbidden at Lite) and
the resulting catalog must pass validate_catalog.
"""

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator.migrate import migrate_dir, translate_browser_test
from smoke_orchestrator.validation import validate_catalog


def _bt(task="Log in and see the dashboard", judge=("dashboard is visible",), **extra):
    doc = {"task": task, "judge_context": list(judge)}
    doc.update(extra)
    return doc


def test_translate_produces_agent_ui_step():
    entry = translate_browser_test(
        _bt(url="/login", max_steps=20, tags=["smoke", "auth"]), test_id="login-flow"
    )
    assert entry["id"] == "login-flow"
    assert entry["tier"] == "Full"
    (step,) = entry["steps"]
    assert step["type"] == "ui" and step["mode"] == "agent"
    assert step["task"] == "Log in and see the dashboard"
    assert step["judge_context"] == ["dashboard is visible"]
    assert step["url"] == "/login"
    assert step["max_steps"] == 20
    assert step["tags"] == ["smoke", "auth"]


def test_translate_forces_full_tier_even_for_smoke_tag():
    # tags:[smoke] must NOT become tier Lite — agent steps may never gate Lite
    entry = translate_browser_test(_bt(tags=["smoke"]), test_id="t")
    assert entry["tier"] == "Full"


def test_translate_omits_absent_optional_fields():
    (step,) = translate_browser_test(_bt(), test_id="t")["steps"]
    assert "url" not in step and "max_steps" not in step and "tags" not in step


def test_migrate_dir_builds_a_valid_catalog(tmp_path):
    src = tmp_path / "browser"
    src.mkdir()
    (src / "login-flow.yaml").write_text(yaml.safe_dump(_bt(url="/login")))
    (src / "checkout.yaml").write_text(
        yaml.safe_dump(_bt(task="Buy an item", judge=("order placed",)))
    )
    catalog = migrate_dir(str(src), app="demo")
    assert catalog["version"] == 1 and catalog["app"] == "demo"
    assert {t["id"] for t in catalog["tests"]} == {"login-flow", "checkout"}
    validate_catalog(catalog)  # must not raise


def test_migrate_dir_rejects_a_file_missing_required_fields(tmp_path):
    src = tmp_path / "browser"
    src.mkdir()
    (src / "bad.yaml").write_text(yaml.safe_dump({"judge_context": ["x"]}))  # no task
    with pytest.raises(ValueError):
        migrate_dir(str(src), app="demo")


class TestCliMigrateSubcommand:
    """The documented copy-paste path must work without PYTHONPATH gymnastics:
    smoke_test.py's cli gains a `migrate` subcommand delegating to migrate.main
    (issue #467 — `python3 -m smoke_orchestrator.migrate` fails from a project
    root because the package is never on sys.path)."""

    def test_cli_migrate_produces_catalog(self, tmp_path):
        from smoke_orchestrator import cli

        src = tmp_path / "browser"
        src.mkdir()
        (src / "login.yaml").write_text(
            "task: Log in and see the dashboard\njudge_context:\n  - dashboard is visible\n"
        )
        out = tmp_path / "smoke-catalog" / "demo.yaml"
        rc = cli.main(["migrate", str(src), "--app", "demo", "--out", str(out)])
        assert rc == 0
        assert out.exists()

    def test_cli_migrate_listed_in_help(self, capsys):
        from smoke_orchestrator import cli

        with pytest.raises(SystemExit):
            cli.main(["--help"])
        assert "migrate" in capsys.readouterr().out
