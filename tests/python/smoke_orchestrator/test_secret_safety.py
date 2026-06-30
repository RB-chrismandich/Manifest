"""US3 — secret safety (T022, SC-006 / FR-013).

No sensitive value may appear in the JUnit XML, the console summary, a step
message, or the persisted state store; a sensitive ref with no env source must
fail clearly with no plaintext fallback.
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator import report as report_mod
from smoke_orchestrator.executor import SmokeTestExecutor
from smoke_orchestrator.redact import Redactor

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLI_TOOL = str(FIXTURES / "cli_tool.py")
SECRET = "supersekret-ABCDEF-12345"


def _write(catalog_dir, app, tests):
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / f"{app}.yaml").write_text(
        yaml.safe_dump({"version": 1, "app": app, "tests": tests}), encoding="utf-8"
    )


def test_secret_absent_from_all_output_sinks(tmp_path, monkeypatch):
    monkeypatch.setenv("BILLING_TOKEN", SECRET)
    # A sensitive step that echoes the env secret to stderr and fails, forcing the
    # secret onto the failure-message path — which must be scrubbed everywhere.
    leak = "import sys; sys.stderr.write(sys.argv[1]); sys.exit(1)"
    _write(
        tmp_path,
        "demo",
        [
            {
                "id": "login",
                "tier": "Lite",
                "steps": [
                    {
                        "name": "auth",
                        "type": "cli",
                        "sensitive": True,
                        "command": [sys.executable, "-c", leak, "${env.BILLING_TOKEN}"],
                    },
                ],
            }
        ],
    )
    redactor = Redactor()
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run(
        "demo", tier="Lite", redactor=redactor
    )

    assert rep.results[0].steps[0].status == "failed"
    assert len(redactor) >= 1, "secret should have been registered for redaction"

    msg = rep.results[0].steps[0].message
    assert SECRET not in msg and "***" in msg  # message already scrubbed

    junit = tmp_path / "out.xml"
    report_mod.write_junit(rep, str(junit), redactor)
    assert SECRET not in junit.read_text()
    assert SECRET not in report_mod.format_summary(rep, redactor)


def test_sensitive_capture_never_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEST_STATE_ROOT", str(tmp_path / "state"))
    cat_dir = tmp_path / "cat"
    _write(
        cat_dir,
        "demo",
        [
            {
                "id": "login",
                "tier": "Lite",
                "steps": [
                    {
                        "name": "auth",
                        "type": "cli",
                        "sensitive": True,
                        "command": [
                            sys.executable,
                            "-c",
                            "print('token=topsecret-XYZ')",
                        ],
                        "captures": {"token": r"token=(\S+)"},
                    },
                ],
            }
        ],
    )
    rep = SmokeTestExecutor(catalog_dir=str(cat_dir), persist_state=True).run(
        "demo", tier="Lite"
    )
    assert rep.exit_code == 0

    state_file = tmp_path / "state" / "smoke" / "state" / "demo.json"
    if (
        state_file.exists()
    ):  # sensitive value must never be written, even with persist on
        text = state_file.read_text()
        assert "topsecret-XYZ" not in text
        assert "token" not in text


def test_sensitive_state_ref_is_redacted(tmp_path):
    """Tier-1 B-2: a ${state.*} value used in a sensitive step is registered for redaction."""
    leak = "import sys; sys.stderr.write(sys.argv[1]); sys.exit(1)"
    _write(
        tmp_path,
        "demo",
        [
            {
                "id": "chain",
                "tier": "Lite",
                "steps": [
                    {
                        "name": "produce",
                        "type": "cli",
                        "command": [sys.executable, "-c", "print('val=SECRETVAL-123')"],
                        "captures": {"val": r"val=(\S+)"},
                    },
                    {
                        "name": "consume",
                        "type": "cli",
                        "sensitive": True,
                        "needs": ["val"],
                        "command": [sys.executable, "-c", leak, "${state.val}"],
                    },
                ],
            }
        ],
    )
    redactor = Redactor()
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run(
        "demo", tier="Lite", redactor=redactor
    )
    consume = rep.results[0].steps[1]
    assert consume.status == "failed"
    assert "SECRETVAL-123" not in consume.message and "***" in consume.message


def test_sensitive_ref_without_env_source_fails_clearly(tmp_path):
    """FR-013: a sensitive ref with no env source is a hard error, not a fallback."""
    _write(
        tmp_path,
        "demo",
        [
            {
                "id": "login",
                "tier": "Lite",
                "steps": [
                    {
                        "name": "auth",
                        "type": "cli",
                        "sensitive": True,
                        "command": [
                            sys.executable,
                            CLI_TOOL,
                            "echo",
                            "${env.DEFINITELY_MISSING_SECRET}",
                        ],
                    },
                ],
            }
        ],
    )
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert rep.results[0].steps[0].status == "failed"
    assert "DEFINITELY_MISSING_SECRET" in rep.results[0].steps[0].message
    assert rep.exit_code == 1
