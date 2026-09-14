"""Regression contracts for shared-check receipt aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manifest_agent.checks.aggregate import aggregate_results
from manifest_agent.checks.registry import load_registry
from test_shared_checks_review_regressions import (
    RECEIPT_NUMERIC_BOOLEAN_MUTATIONS,
    RECEIPT_SHAPE_MUTATIONS,
    context,
    invoke_aggregate_cli,
    receipt,
    registry,
)


@pytest.mark.parametrize("mutate", RECEIPT_SHAPE_MUTATIONS)
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


@pytest.mark.parametrize(
    "mutate", RECEIPT_SHAPE_MUTATIONS + RECEIPT_NUMERIC_BOOLEAN_MUTATIONS
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
    result = invoke_aggregate_cli(config, results_dir, context_path)
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
    result = invoke_aggregate_cli(config, results_dir, context_path)
    assert result.exit_code == 3
    assert json.loads(result.output)["status"] == "BLOCKED"
    assert "Traceback" not in result.output
