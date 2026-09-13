"""Slice A contracts for truthful local shared checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from manifest_agent.checks.aggregate import aggregate_results
from manifest_agent.checks.candidate import candidate_digest, materialize_candidate
from manifest_agent.checks.debt import evaluate_findings
from manifest_agent.checks.debt_baseline import load_baseline
from manifest_agent.checks.registry import load_registry, resolve_checks
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


def candidate(tmp_path: Path, exit_code: int = 0):
    source = tmp_path / "source"
    source.mkdir()
    (source / "probe.py").write_text(f"raise SystemExit({exit_code})\n")
    return materialize_candidate(source, tmp_path / "candidate")


def candidate_with_policies(
    tmp_path: Path,
    *,
    baseline: object = (),
    invariants: object = (
        {
            "id": "shared-checks.exit-status",
            "description": "PASS=0, FAIL=2, BLOCKED=3",
        },
    ),
    script: str = "raise SystemExit(0)\n",
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
        json.dumps({"schema_version": 1, "invariants": invariants}), encoding="utf-8"
    )
    return materialize_candidate(source, tmp_path / "candidate")


def test_invalid_config_and_argv_are_rejected(tmp_path):
    bad = registry(tmp_path / "checks.json", argv=["sh", "-c", "exit 0"])
    with pytest.raises(ValueError, match="string evaluation"):
        load_registry(bad)
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_registry(bad)


def test_selection_is_deterministic_and_base_is_resolved(tmp_path):
    config = registry(tmp_path / "checks.json")
    loaded = load_registry(config)
    assert [check.id for check in resolve_checks(loaded, "full", "test")] == [
        "test.probe"
    ]
    result = CliRunner().invoke(
        cli,
        [
            "check",
            "full",
            "--project-config",
            str(config),
            "--base",
            "HEAD",
            "--json",
        ],
    )
    assert result.exit_code in {2, 3}
    assert json.loads(result.output)["base_sha"]


@pytest.mark.parametrize("honors,expected", [(True, "BLOCKED"), (False, "FAIL")])
def test_exit_three_honors_only_repo_owned_contract(tmp_path, honors, expected):
    executable = (
        [sys.executable, "tools/project_checks/probe.py"]
        if honors
        else [sys.executable, "probe.py"]
    )
    root = tmp_path / "root"
    root.mkdir()
    script = root / ("tools/project_checks/probe.py" if honors else "probe.py")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("raise SystemExit(3)\n")
    config = registry(tmp_path / "checks.json", argv=executable, honors=honors)
    check = load_registry(config)["checks"][0]
    result = execute_check(
        check, materialize_candidate(root, tmp_path / "candidate"), {}
    )
    assert result.status == expected


def receipt(status="PASS", *, head="head", attempt=1):
    return {
        "schema_version": 1,
        "profile": "full",
        "group": "test",
        "head_sha": head,
        "base_sha": "base",
        "candidate_digest": "candidate",
        "config_digest": "config",
        "required_ids": ["test.probe"],
        "results": [{"id": "test.probe", "status": status, "returncode": 0}],
        "status": status,
        "run_attempt": attempt,
        "artifact_id": "artifact",
    }


def context(*, attempt=1, head="head"):
    return {
        "tested_sha": head,
        "base_sha": "base",
        "candidate_digest": "candidate",
        "config_digest": "config",
        "run_attempt": attempt,
        "producer_jobs": [
            {
                "group": "test",
                "conclusion": "success",
                "artifact_id": "artifact",
                "run_attempt": attempt,
            }
        ],
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipts, ctx: receipts.clear(),
        lambda receipts, ctx: receipts.append(receipt()),
        lambda receipts, ctx: receipts.__setitem__(0, receipt(head="stale")),
        lambda receipts, ctx: receipts.__setitem__(0, receipt(attempt=2)),
        lambda receipts, ctx: receipts[0]["results"].clear(),
    ],
)
def test_aggregate_blocks_missing_stale_duplicate_wrong_attempt_or_inert_receipts(
    tmp_path, mutate
):
    loaded = load_registry(registry(tmp_path / "checks.json"))
    receipts, run_context = [receipt()], context()
    mutate(receipts, run_context)
    assert (
        aggregate_results(loaded, "full", receipts, run_context)["status"] == "BLOCKED"
    )


def test_candidate_identity_is_stable_and_baseline_cannot_hide_new_finding(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "probe.py").write_text("raise SystemExit(0)\n")
    first = materialize_candidate(source, tmp_path / "first")
    second = materialize_candidate(source, tmp_path / "second")
    assert first.digest == second.digest
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"schema_version": 1, "findings": [{"id": "old"}]}))
    from manifest_agent.checks.debt import evaluate_findings

    assert (
        evaluate_findings([{"id": "old"}, {"id": "new"}], baseline)["status"] == "FAIL"
    )


def test_empty_selection_is_blocked(tmp_path):
    loaded = load_registry(registry(tmp_path / "checks.json"))
    report = run_profile(loaded, "full", "lint", candidate(tmp_path), {})
    assert report["status"] == "BLOCKED"


def test_candidate_rejects_links_and_special_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "outside"
    target.write_text("outside")
    (source / "absolute").symlink_to(target)
    with pytest.raises(RuntimeError, match="symlink"):
        materialize_candidate(source, tmp_path / "candidate")


def test_mutating_check_is_blocked_after_execution(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "probe.py").write_text(
        "from pathlib import Path\nPath('protected.py').unlink()\n"
    )
    (source / "protected.py").write_text("protected\n")
    config = registry(tmp_path / "checks.json")
    report = run_profile(
        load_registry(config),
        "full",
        None,
        materialize_candidate(source, tmp_path / "candidate"),
        {},
    )
    assert report["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt, run_context: receipt.pop("head_sha"),
        lambda receipt, run_context: receipt.__setitem__("run_attempt", "1"),
        lambda receipt, run_context: receipt.__setitem__("status", "FAIL"),
        lambda receipt, run_context: receipt.__setitem__("artifact_id", "wrong"),
        lambda receipt, run_context: receipt["results"][0].__setitem__(
            "id", "other.group"
        ),
        lambda receipt, run_context: run_context.pop("tested_sha"),
        lambda receipt, run_context: run_context["producer_jobs"].append(
            dict(run_context["producer_jobs"][0])
        ),
    ],
)
def test_aggregate_rejects_incomplete_or_forged_provenance(tmp_path, mutate):
    loaded = load_registry(registry(tmp_path / "checks.json"))
    item, run_context = receipt(), context()
    mutate(item, run_context)
    assert aggregate_results(loaded, "full", [item], run_context)["status"] == "BLOCKED"


def test_aggregate_rejects_receipt_context_pair_from_old_registry(tmp_path):
    config = registry(tmp_path / "checks.json")
    old_registry = load_registry(config)
    item, run_context = receipt(), context()
    item["config_digest"] = old_registry["config_digest"]
    run_context["config_digest"] = old_registry["config_digest"]
    registry(config, argv=[sys.executable, "different-probe.py"])
    current_registry = load_registry(config)

    report = aggregate_results(current_registry, "full", [item], run_context)

    assert report["status"] == "BLOCKED"
    assert "context config_digest mismatch" in report["diagnostics"]


def test_candidate_digest_has_unambiguous_record_boundaries(tmp_path):
    one_file = tmp_path / "one"
    one_file.mkdir()
    (one_file / "a").write_bytes(b"X\0file\0b\0Y")
    two_files = tmp_path / "two"
    two_files.mkdir()
    (two_files / "a").write_bytes(b"X")
    (two_files / "b").write_bytes(b"Y")

    assert candidate_digest(one_file) != candidate_digest(two_files)


def test_retargeting_internal_symlink_during_check_blocks_candidate_pass(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    policy_dir = source / "config"
    policy_dir.mkdir()
    (policy_dir / "debt-baseline.json").write_text(
        '{"schema_version":1,"findings":[]}', encoding="utf-8"
    )
    (policy_dir / "check-preservation.json").write_text(
        '{"schema_version":1,"invariants":[{"id":"shared-checks.exit-status","description":"valid"}]}',
        encoding="utf-8",
    )
    (source / "first.py").write_text("value = 1\n", encoding="utf-8")
    (source / "second.py").write_text("value = 2\n", encoding="utf-8")
    (source / "active.py").symlink_to("first.py")
    (source / "probe.py").write_text(
        "from pathlib import Path\n"
        "Path('active.py').unlink()\n"
        "Path('active.py').symlink_to('second.py')\n",
        encoding="utf-8",
    )
    before = candidate_digest(source)
    candidate_copy = materialize_candidate(source, tmp_path / "candidate")
    config = registry(tmp_path / "checks.json")

    report = run_profile(load_registry(config), "full", None, candidate_copy, {})

    assert candidate_digest(source) == before
    assert report["status"] == "BLOCKED"
    assert "candidate content changed during check execution" in report["diagnostics"]


@pytest.mark.parametrize(
    "baseline,invariants",
    [
        (None, ({"id": "shared-checks.exit-status", "description": "valid"},)),
        ([None], ({"id": "shared-checks.exit-status", "description": "valid"},)),
        ((), None),
        ((), [{"id": None, "description": "valid"}]),
        ((), [{"id": "unknown", "description": "valid"}]),
    ],
)
def test_malformed_or_unknown_declared_policy_blocks_execution(
    tmp_path, baseline, invariants
):
    report = run_profile(
        load_registry(registry(tmp_path / "checks.json")),
        "full",
        None,
        candidate_with_policies(tmp_path, baseline=baseline, invariants=invariants),
        {},
    )

    assert report["status"] == "BLOCKED"


def test_new_debt_finding_is_not_hidden_by_known_baseline(tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"schema_version": 1, "findings": [{"id": "known-debt"}]}),
        encoding="utf-8",
    )

    report = evaluate_findings([{"id": "known-debt"}, {"id": "new-debt"}], baseline)

    assert report == {"status": "FAIL", "new_findings": ["new-debt"]}


@pytest.mark.parametrize(
    "findings",
    [
        None,
        [None],
        [{"id": None}],
        [{"id": "duplicate"}, {"id": "duplicate"}],
    ],
)
def test_debt_baseline_rejects_malformed_findings(tmp_path, findings):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"schema_version": 1, "findings": findings}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="debt baseline"):
        load_baseline(baseline)


def test_aggregate_rejects_changed_candidate_or_configuration(tmp_path):
    loaded = load_registry(registry(tmp_path / "checks.json"))
    item, run_context = receipt(), context()
    item["candidate_digest"] = "changed"
    run_context["candidate_digest"] = "candidate"
    item["config_digest"] = "old"
    run_context["config_digest"] = "new"
    assert aggregate_results(loaded, "full", [item], run_context)["status"] == "BLOCKED"
