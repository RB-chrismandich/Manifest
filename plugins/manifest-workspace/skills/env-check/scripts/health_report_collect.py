"""Observation planning and report assembly stages."""
# ruff: noqa: F405

from __future__ import annotations

import importlib.metadata
import os
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from health_report_common import *  # noqa: F403
from health_report_inspect import _inspect_installation, _inspect_pins, _inspect_receipt
from health_report_sanitize import (
    _extract_version,
    _sanitize_hook,
    _sanitize_inventory,
    _sanitize_mcp,
    _status_for_harness,
)


def _observation_result(
    observation: Observation,
    deadline: float,
    monotonic: Monotonic,
    runner: Runner,
    environment: Mapping[str, str],
) -> CommandResult:
    remaining = deadline - monotonic()
    outer_timeout = min(observation.limit_seconds, remaining)
    if outer_timeout <= 0:
        return CommandResult("timeout")
    argv = observation.argv
    if observation.kind == "mcp":
        inner_timeout = outer_timeout - NESTED_PROBE_CLEANUP_SECONDS
        if inner_timeout <= 0:
            return CommandResult("timeout")
        timeout_index = argv.index("--timeout-seconds") + 1
        argv = (
            *argv[:timeout_index],
            f"{inner_timeout:.6f}",
            *argv[timeout_index + 1 :],
        )
    return runner(argv, outer_timeout, environment)


def _collect_observations(
    observations: Sequence[Observation],
    deadline: float,
    monotonic: Monotonic,
    runner: Runner,
    environment: Mapping[str, str],
) -> dict[str, CommandResult]:
    results: dict[str, CommandResult] = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = {
        executor.submit(
            _observation_result,
            observation,
            deadline,
            monotonic,
            runner,
            environment,
        ): observation
        for observation in observations
    }
    try:
        timeout = max(0.0, deadline - monotonic())
        done, pending = concurrent.futures.wait(futures, timeout=timeout)
        for future in done:
            observation = futures[future]
            try:
                results[observation.key] = future.result()
            except Exception:
                results[observation.key] = CommandResult("unavailable")
        for future in pending:
            observation = futures[future]
            future.cancel()
            results[observation.key] = CommandResult("timeout")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _plan_mcp_observations(
    requested: Sequence[str],
    environment: Mapping[str, str],
    runtime_dir: Path,
    python: str | None,
    findings: list[dict[str, str]],
) -> list[Observation]:
    observations: list[Observation] = []
    if not python:
        for harness in requested:
            _add_finding(findings, "health_python_missing", "installation", harness)
        return observations
    for harness in requested:
        arguments = [
            python,
            str(runtime_dir / "mcp_health.py"),
            "--json",
            "--harness",
            harness,
        ]
        if harness == "claude":
            arguments.append("--probe")
        arguments.extend(
            [
                "--timeout-seconds",
                "20",
                "--state-dir",
                str(_state_home(environment) / "manifest/health"),
            ]
        )
        observations.append(
            Observation(f"mcp:{harness}", "mcp", harness, tuple(arguments), 20.0)
        )
    if "claude" in requested:
        observations.append(
            Observation(
                "hooks",
                "hooks",
                "claude",
                (
                    python,
                    str(runtime_dir / "hook_smoke.py"),
                    "--json",
                    "--state-dir",
                    str(_state_home(environment) / "manifest/health"),
                    "--timeout-seconds",
                    "30",
                ),
                30.0,
            )
        )
    return observations


def _plan_version_observations(
    requested: Sequence[str],
    executables: dict[str, str],
    observations: list[Observation],
    findings: list[dict[str, str]],
) -> None:
    for harness in requested:
        executable = executables.get(harness)
        if executable:
            observations.append(
                Observation(
                    f"version:{harness}",
                    "version",
                    harness,
                    (executable, "--version"),
                    5.0,
                )
            )
        else:
            _add_finding(findings, "native_cli_missing", "version", harness)


def _plan_observations(
    requested: Sequence[str],
    environment: Mapping[str, str],
    runtime_dir: Path,
    executables: dict[str, str],
    receipt: dict[str, Any] | None,
    source_root: Path | None,
    findings: list[dict[str, str]],
) -> tuple[list[Observation], list[str]]:
    python = executables.get("python")
    observations = _plan_mcp_observations(
        requested, environment, runtime_dir, python, findings
    )
    _plan_version_observations(requested, executables, observations, findings)
    coordinator_names = sorted(
        set(receipt.get("harnesses", {})) & COORDINATOR_HARNESSES
        if receipt is not None
        else set(requested) & COORDINATOR_HARNESSES
    )
    coordinator = executables.get("coordinator")
    if coordinator_names and coordinator and source_root is not None:
        argv = [coordinator, "reconcile", "--source", str(source_root), "--json"]
        for harness in coordinator_names:
            argv.extend(["--harness", harness])
        observations.append(
            Observation("inventory", "inventory", None, tuple(argv), 5.0)
        )
    elif coordinator_names:
        for harness in coordinator_names:
            _add_finding(findings, "inventory_unavailable", "inventory", harness)

    return observations, coordinator_names


def _sanitize_stages(
    requested: Sequence[str],
    results: dict[str, CommandResult],
    installation: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    coordinator_names: list[str],
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    mcp: dict[str, Any] = {}
    for harness in requested:
        result = results.get(f"mcp:{harness}")
        if result is None:
            _add_finding(findings, "mcp_unavailable", "mcp", harness)
            mcp[harness] = {"status": "degraded", "servers": []}
        else:
            mcp[harness] = _sanitize_mcp(result, harness, findings)

    if "claude" in requested:
        hook_result = results.get("hooks", CommandResult("unavailable"))
        baseline_hashes = installation.get("hook_hashes") if installation else None
        hooks = _sanitize_hook(hook_result, baseline_hashes, findings)
    else:
        hooks = {"status": "not_applicable", "hashes": {}, "checks": [], "findings": []}

    inventories = (
        _sanitize_inventory(
            results.get("inventory", CommandResult("unavailable")),
            receipt,
            coordinator_names,
            findings,
        )
        if coordinator_names and "inventory" in results
        else {
            name: {"status": "degraded", "state": "unavailable"}
            for name in coordinator_names
        }
    )

    return mcp, hooks, inventories


def _inventory_status(inventory: dict[str, Any] | None, harness: str) -> str:
    return (
        inventory["status"]
        if inventory is not None
        else ("native" if harness == "omp" else "not_observed")
    )


def _harness_summary_row(
    requested: bool, version: str | None, version_status: str, inventory_status: str
) -> dict[str, Any]:
    return {
        "status": "ok",
        "requested": requested,
        "version": version,
        "version_status": version_status,
        "inventory_status": inventory_status,
    }


def _summarize_harnesses(
    requested: Sequence[str],
    receipt: dict[str, Any] | None,
    results: dict[str, CommandResult],
    inventories: dict[str, dict[str, Any]],
    pin_values: dict[str, str],
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    harness_summary: dict[str, Any] = {}
    all_harnesses = sorted(
        set(requested) | set(receipt.get("harnesses", {}) if receipt else {})
    )
    for harness in all_harnesses:
        requested_harness = harness in requested
        version_result = (
            results.get(f"version:{harness}") if requested_harness else None
        )
        receipt_record = (
            receipt.get("harnesses", {}).get(harness) if receipt is not None else None
        )
        version_status = "not_observed"
        observed_version: str | None = None
        if version_result is None and isinstance(receipt_record, dict):
            _add_finding(findings, "version_not_observed", "version", harness)
        if version_result is not None:
            if version_result.outcome == "timeout":
                _add_finding(findings, "version_timeout", "version", harness)
                version_status = "degraded"
            elif version_result.outcome != "complete" or version_result.returncode != 0:
                _add_finding(findings, "native_cli_missing", "version", harness)
                version_status = "degraded"
            else:
                observed_version = _extract_version(version_result.stdout)
                if observed_version is None:
                    _add_finding(findings, "version_unparseable", "version", harness)
                    version_status = "degraded"
                else:
                    expected_version: str | None = None
                    if harness == "omp":
                        expected_version = pin_values.get("omp")
                    elif isinstance(receipt_record, dict):
                        expected_version = _extract_version(
                            receipt_record["native_version"]
                        )
                    if expected_version is None or observed_version != expected_version:
                        _add_finding(
                            findings, "native_version_drift", "version", harness
                        )
                        version_status = "degraded"
                    else:
                        version_status = "ok"
        inventory = inventories.get(harness)
        inventory_status = _inventory_status(inventory, harness)
        harness_summary[harness] = _harness_summary_row(
            requested_harness, observed_version, version_status, inventory_status
        )

    return harness_summary


def collect_report(
    *,
    harnesses: Sequence[str],
    environment: Mapping[str, str] | None = None,
    runtime_dir: Path | None = None,
    clock: Clock = utc_now,
    monotonic: Monotonic = time.monotonic,
    runner: Runner = run_bounded,
    package_version: PackageVersion = importlib.metadata.version,
) -> dict[str, Any]:
    """Collect all observations under one aggregate deadline."""
    environment = dict(os.environ if environment is None else environment)
    requested = tuple(dict.fromkeys(harnesses))
    runtime_dir = (runtime_dir or Path(__file__).resolve().parent).resolve()
    started = monotonic()
    observation_deadline = started + OBSERVATION_SECONDS
    now = clock()
    findings: list[dict[str, str]] = []
    installation, source_root, executables = _inspect_installation(
        environment, runtime_dir, findings
    )
    pins, pin_values = _inspect_pins(environment, package_version, findings)
    receipt_path = _state_home(environment) / "manifest/installation.json"
    receipt_summary, receipt, _expected_bundles = _inspect_receipt(
        receipt_path, source_root, requested, now, findings
    )
    receipt_summary["installation"] = (
        "ok"
        if not any(item["component"] == "installation" for item in findings)
        else "degraded"
    )
    observations, coordinator_names = _plan_observations(
        requested, environment, runtime_dir, executables, receipt, source_root, findings
    )
    results = _collect_observations(
        observations, observation_deadline, monotonic, runner, environment
    )
    mcp, hooks, inventories = _sanitize_stages(
        requested, results, installation, receipt, coordinator_names, findings
    )
    harness_summary = _summarize_harnesses(
        requested, receipt, results, inventories, pin_values, findings
    )
    return _assemble_report(
        now, findings, receipt_summary, harness_summary, mcp, pins, hooks
    )


def _assemble_report(
    now: datetime,
    findings: list[dict[str, str]],
    receipt_summary: dict[str, Any],
    harness_summary: dict[str, Any],
    mcp: dict[str, Any],
    pins: dict[str, Any],
    hooks: dict[str, Any],
) -> dict[str, Any]:
    """Derive component statuses from sorted findings and build the report."""
    findings.sort(
        key=lambda item: (item["component"], item.get("harness", ""), item["code"])
    )
    for harness, summary in harness_summary.items():
        summary["status"] = _status_for_harness(findings, harness)
    receipt_summary["status"] = (
        "degraded"
        if any(item["component"] in {"receipt", "installation"} for item in findings)
        else "ok"
    )
    pins["status"] = (
        "degraded" if any(item["component"] == "pins" for item in findings) else "ok"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _timestamp(now),
        "status": "degraded" if findings else "ok",
        "receipt": receipt_summary,
        "harnesses": harness_summary,
        "mcp": mcp,
        "pins": pins,
        "hooks": hooks,
        "findings": findings,
    }
