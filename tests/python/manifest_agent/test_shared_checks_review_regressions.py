"""Regression contracts for the Slice A review findings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from manifest_agent.checks.aggregate import aggregate_results
from manifest_agent.checks.candidate import candidate_digest, materialize_candidate
from manifest_agent.checks.receipt import validate_receipt
from manifest_agent.checks.registry import load_registry
from manifest_agent.checks.runner import execute_check, run_profile
from manifest_agent.cli import cli


def registry(
    path: Path, *, argv: list[str] | None = None, honors: bool = False
) -> Path:
    policy_dir = path.parent / "config"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "debt-baseline.json").write_text(
        '{"schema_version":1,"findings":[]}', encoding="utf-8"
    )
    (policy_dir / "check-preservation.json").write_text(
        '{"schema_version":1,"invariants":[{"id":"shared-checks.exit-status","description":"valid"}]}',
        encoding="utf-8",
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checks": [
                    {
                        "id": "test.probe",
                        "group": "test",
                        "category": "test",
                        "argv": argv or [sys.executable, "probe.py"],
                        "cwd": ".",
                        "inputs": ["probe.py"],
                        "dependencies": [],
                        "timeout_seconds": 2,
                        "selection": "project",
                        "tool": "python",
                        "version": "fixture",
                        "honors_status_contract": honors,
                    }
                ],
                "profiles": {
                    name: ["test.probe"]
                    for name in ("quick", "full", "security", "release")
                },
                "debt_baseline": "config/debt-baseline.json",
                "preservation": "config/check-preservation.json",
            }
        ),
        encoding="utf-8",
    )
    return path


def candidate_with_policies(
    tmp_path: Path, *, baseline: object = (), script: str = "raise SystemExit(0)\n"
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "probe.py").write_text(script, encoding="utf-8")
    config = source / "config"
    config.mkdir()
    (config / "debt-baseline.json").write_text(
        json.dumps({"schema_version": 1, "findings": baseline}), encoding="utf-8"
    )
    (config / "check-preservation.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "invariants": [
                    {"id": "shared-checks.exit-status", "description": "valid"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return materialize_candidate(source, tmp_path / "candidate")


def receipt() -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile": "full",
        "group": "test",
        "head_sha": "head",
        "base_sha": "base",
        "candidate_digest": "candidate",
        "config_digest": "config",
        "required_ids": ["test.probe"],
        "results": [{"id": "test.probe", "status": "PASS", "returncode": 0}],
        "status": "PASS",
        "run_attempt": 1,
        "artifact_id": "artifact",
    }


def context() -> dict[str, object]:
    return {
        "tested_sha": "head",
        "base_sha": "base",
        "candidate_digest": "candidate",
        "config_digest": "config",
        "run_attempt": 1,
        "producer_jobs": [
            {
                "group": "test",
                "conclusion": "success",
                "artifact_id": "artifact",
                "run_attempt": 1,
            }
        ],
    }


def test_candidate_digest_covers_empty_directories_and_modes(tmp_path: Path):
    root = tmp_path / "candidate"
    root.mkdir()
    probe = root / "probe.py"
    probe.write_text("pass\n", encoding="utf-8")
    baseline = candidate_digest(root)
    (root / "empty").mkdir()
    assert candidate_digest(root) != baseline
    (root / "empty").rmdir()
    probe.chmod(0o755)
    assert candidate_digest(root) != baseline


@pytest.mark.parametrize(
    "argv",
    [
        ["env", "X=1"],
        ["env", "X=1", "bash", "-c", "exit 0"],
        ["bash", "-lc", "exit 0"],
        ["/bin/bash", "-c", "exit 0"],
        ["/usr/bin/csh", "-c", "exit 0"],
        ["/usr/local/bin/tcsh", "-c", "exit 0"],
        ["/opt/pwsh", "-c", "exit 0"],
        ["/opt/powershell", "-c", "exit 0"],
        ["tools/project_checks/bash", "-c", "exit 0"],
        ["nice"],
        ["nice", "bash", "-c", "exit 0"],
        ["nohup", "bash", "-c", "exit 0"],
        ["timeout", "10", "bash", "-c", "exit 0"],
        ["busybox", "sh", "-c", "exit 0"],
        ["setsid", "bash", "-c", "exit 0"],
        ["setsid", "/bin/ash", "-c", "exit 0"],
        ["stdbuf", "yash", "-c", "exit 0"],
        ["taskset", "mksh", "-c", "exit 0"],
        ["chrt", "bash", "-c", "exit 0"],
        ["ionice", "bash", "-c", "exit 0"],
        ["cmd", "/c", "exit 0"],
        ["cmd.exe", "/c", "exit 0"],
        ["powershell.exe", "-Command", "exit 0"],
        ["pwsh.exe", "-Command", "exit 0"],
    ],
)
def test_registry_rejects_inert_or_shell_wrapper_argv(tmp_path: Path, argv: list[str]):
    with pytest.raises(ValueError, match=r"(?:command|launcher|shell)"):
        load_registry(registry(tmp_path / "checks.json", argv=argv))


@pytest.mark.parametrize(
    "argv",
    [
        ["/bin/sh", "-c", "exit 0"],
        ["/usr/bin/env", "bash", "-c", "exit 0"],
        ["env", "sh", "-c", "exit 0"],
    ],
)
def test_registry_rejects_shell_strings_through_supported_wrappers(
    tmp_path: Path, argv: list[str]
):
    with pytest.raises(ValueError, match="shell"):
        load_registry(registry(tmp_path / "checks.json", argv=argv))


def test_registry_consumes_env_assignments_before_command(tmp_path: Path):
    loaded = load_registry(
        registry(
            tmp_path / "checks.json",
            argv=["env", "X=1", sys.executable, "tools/project_checks/probe.py"],
            honors=True,
        )
    )
    assert loaded["checks"][0].argv[2] == sys.executable


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema_version=True),
        lambda value: value.update(run_attempt=True),
        lambda value: value["results"][0].update(returncode=False),
        lambda value: value["results"][0].update(duration_seconds=False),
    ],
)
def test_receipt_rejects_json_booleans_for_numeric_fields(mutate):
    malformed = receipt()
    mutate(malformed)
    assert validate_receipt(malformed)


def test_registry_rejects_json_boolean_timeout(tmp_path: Path):
    config = registry(tmp_path / "checks.json")
    document = json.loads(config.read_text(encoding="utf-8"))
    document["checks"][0]["timeout_seconds"] = True
    config.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="schema validation"):
        load_registry(config)


def test_large_structured_findings_are_not_lost_to_diagnostic_truncation(
    tmp_path: Path,
):
    candidate_copy = candidate_with_policies(
        tmp_path,
        script=(
            "import json\n"
            "print(json.dumps({'findings': [{'id': f'new-{i:05d}'} "
            "for i in range(9000)]}))\n"
        ),
    )
    report = run_profile(
        load_registry(registry(tmp_path / "checks.json")),
        "full",
        None,
        candidate_copy,
        {},
    )
    assert report["status"] == "FAIL"
    assert len(report["results"][0]["findings"]) == 9000
    assert "new debt findings: new-00000" in report["diagnostics"][0]


def test_registry_rejects_traversal_before_repo_owned_classification(tmp_path: Path):
    with pytest.raises(ValueError, match="candidate-relative"):
        load_registry(
            registry(
                tmp_path / "checks.json",
                argv=[sys.executable, "tools/project_checks/../outside.py"],
                honors=True,
            )
        )


def test_structured_check_findings_fail_new_debt(tmp_path: Path):
    candidate_copy = candidate_with_policies(
        tmp_path,
        baseline=[{"id": "known"}],
        script=(
            "import json\n"
            "print(json.dumps({'findings': [{'id': 'known'}, {'id': 'new'}]}))\n"
        ),
    )
    report = run_profile(
        load_registry(registry(tmp_path / "checks.json")),
        "full",
        None,
        candidate_copy,
        {},
    )
    assert report["status"] == "FAIL"
    assert report["results"][0]["findings"] == ({"id": "known"}, {"id": "new"})
    assert "new debt findings: new" in report["diagnostics"]


def test_invalid_policy_short_circuits_before_execution(tmp_path: Path):
    candidate_copy = candidate_with_policies(
        tmp_path,
        baseline=None,
        script="from pathlib import Path\nPath('ran').write_text('yes')\n",
    )
    report = run_profile(
        load_registry(registry(tmp_path / "checks.json")),
        "full",
        None,
        candidate_copy,
        {},
    )
    assert report["status"] == "BLOCKED"
    assert report["results"] == []
    assert not (candidate_copy.root / "ran").exists()


def test_project_checks_schema_is_strict_and_matches_runtime_shape():
    schema = json.loads(
        (Path(__file__).parents[3] / "schemas/project-checks.schema.json").read_text(
            encoding="utf-8"
        )
    )
    check = schema["properties"]["checks"]["items"]
    assert {
        "id",
        "group",
        "category",
        "argv",
        "cwd",
        "inputs",
        "dependencies",
        "timeout_seconds",
        "selection",
        "tool",
        "version",
        "honors_status_contract",
    } <= set(check["required"])
    assert check["additionalProperties"] is False
    assert schema["properties"]["profiles"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(group=[]),
        lambda value: value.update(status=[]),
        lambda value: value.update(required_ids=[["test.probe"]]),
        lambda value: value.update(
            results=[{"id": ["test.probe"], "status": ["PASS"], "returncode": []}]
        ),
    ],
)
def test_malformed_receipt_shapes_short_circuit_to_blocked(tmp_path: Path, mutate):
    malformed = receipt()
    mutate(malformed)
    assert validate_receipt(malformed)
    report = aggregate_results(
        load_registry(registry(tmp_path / "checks.json")),
        "full",
        [malformed],
        context(),
    )
    assert report["status"] == "BLOCKED"


def test_repo_owned_exit_two_is_fail_with_diagnostics(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    script = root / "tools/project_checks/probe.py"
    script.parent.mkdir(parents=True)
    script.write_text("import sys\nprint('detail', file=sys.stderr)\nsys.exit(2)\n")
    check = load_registry(
        registry(
            tmp_path / "checks.json",
            argv=[sys.executable, "tools/project_checks/probe.py"],
            honors=True,
        )
    )["checks"][0]
    result = execute_check(
        check, materialize_candidate(root, tmp_path / "candidate"), {}
    )
    assert result.status == "FAIL"
    assert result.diagnostics == "detail\n"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(group=[]),
        lambda value: value.update(status=[]),
        lambda value: value.update(required_ids=[["test.probe"]]),
        lambda value: value.update(
            results=[{"id": ["test.probe"], "status": ["PASS"], "returncode": []}]
        ),
        lambda value: value.update(schema_version=True),
        lambda value: value.update(run_attempt=True),
        lambda value: value["results"][0].update(returncode=False),
        lambda value: value["results"][0].update(duration_seconds=False),
    ],
)
def test_malformed_receipt_cli_blocks_without_traceback(tmp_path: Path, mutate):
    config = registry(tmp_path / "checks.json")
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    malformed = receipt()
    mutate(malformed)
    (results_dir / "receipt.json").write_text(json.dumps(malformed), encoding="utf-8")
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(context()), encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        [
            "check-aggregate",
            "full",
            "--project-config",
            str(config),
            "--results-dir",
            str(results_dir),
            "--context",
            str(context_path),
            "--json",
        ],
    )
    assert result.exit_code == 3
    assert json.loads(result.output)["status"] == "BLOCKED"
    assert "Traceback" not in result.output


@pytest.mark.parametrize("malformed_context", [[], {"producer_jobs": None}])
def test_malformed_aggregate_context_blocks_without_exception(
    tmp_path: Path, malformed_context
):
    report = aggregate_results(
        load_registry(registry(tmp_path / "checks.json")),
        "full",
        [receipt()],
        malformed_context,
    )

    assert report["status"] == "BLOCKED"
    assert report["diagnostics"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(run_attempt=True),
        lambda value: value["producer_jobs"][0].update(run_attempt=True),
    ],
)
def test_boolean_aggregate_context_blocks_at_direct_and_cli_boundaries(
    tmp_path: Path, mutate
):
    malformed = context()
    mutate(malformed)
    config = registry(tmp_path / "checks.json")
    loaded = load_registry(config)
    assert (
        aggregate_results(loaded, "full", [receipt()], malformed)["status"] == "BLOCKED"
    )

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "receipt.json").write_text(json.dumps(receipt()), encoding="utf-8")
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(malformed), encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        [
            "check-aggregate",
            "full",
            "--project-config",
            str(config),
            "--results-dir",
            str(results_dir),
            "--context",
            str(context_path),
            "--json",
        ],
    )
    assert result.exit_code == 3
    assert json.loads(result.output)["status"] == "BLOCKED"
    assert "Traceback" not in result.output
