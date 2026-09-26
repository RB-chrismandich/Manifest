#!/usr/bin/env python3
"""Observe configured MCP servers without persisting native command output."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_health_expectations import (  # noqa: E402
    INTERNAL_SERVER_NAMES,
    MAX_SERVER_COUNT,
    SERVER_NAME_RE,
    Expectations,
    RuntimePaths,
    _plugin_mcp_expectations,
    load_claude_expectations,
    load_omp_expectations,
)
from mcp_health_report import (  # noqa: E402
    ANSI_RE,
    MAX_CACHE_AGE_SECONDS,
    VALID_REASONS,
    VALID_STATUSES,
    _append_degraded_row,
    _base_rows,
    _cache_path,
    _configuration_row,
    _fresh_cached_report,
    _not_probed_report,
    _parse_cached_timestamp,
    _parse_claude_status,
    _reconcile_cached,
    _report,
    _row,
    _validated_cached_report,
    probe_claude,
    probe_omp,
)
from mcp_health_runtime import (  # noqa: E402
    MAX_OUTPUT_BYTES,
    SCHEMA_VERSION,
    Clock,
    CommandResult,
    Runner,
    _atomic_write_report,
    _kill_process_group,
    _prepare_state_dir,
    _read_json_object,
    _release_probe_lock,
    _timestamp,
    _try_probe_lock,
    run_bounded,
    utc_now,
)

__all__ = [
    "ANSI_RE",
    "INTERNAL_SERVER_NAMES",
    "MAX_CACHE_AGE_SECONDS",
    "MAX_OUTPUT_BYTES",
    "MAX_SERVER_COUNT",
    "MAX_TIMEOUT_SECONDS",
    "SCHEMA_VERSION",
    "SERVER_NAME_RE",
    "VALID_REASONS",
    "VALID_STATUSES",
    "Clock",
    "CommandResult",
    "Expectations",
    "Runner",
    "RuntimePaths",
    "_append_degraded_row",
    "_atomic_write_report",
    "_base_rows",
    "_cache_path",
    "_configuration_row",
    "_fresh_cached_report",
    "_kill_process_group",
    "_not_probed_report",
    "_parse_cached_timestamp",
    "_parse_claude_status",
    "_plugin_mcp_expectations",
    "_prepare_state_dir",
    "_read_json_object",
    "_reconcile_cached",
    "_release_probe_lock",
    "_report",
    "_row",
    "_timestamp",
    "_try_probe_lock",
    "_validated_cached_report",
    "build_parser",
    "collect_health",
    "load_claude_expectations",
    "load_omp_expectations",
    "main",
    "probe_claude",
    "probe_omp",
    "render_text",
    "run_bounded",
    "utc_now",
]

MAX_TIMEOUT_SECONDS = 20.0


def collect_health(
    *,
    harness: str,
    probe: bool,
    timeout_seconds: float,
    paths: RuntimePaths,
    environment: Mapping[str, str],
    inventory_observed: bool,
    observed_servers: Sequence[str],
    runner: Runner = run_bounded,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    """Collect cached or freshly probed health and persist fresh reports."""
    expectations = (
        load_claude_expectations(paths, required=True)
        if harness == "claude"
        else load_omp_expectations(paths)
    )
    if not probe:
        cached = _fresh_cached_report(paths, harness, expectations, clock)
        return cached or _not_probed_report(harness, expectations, clock)

    lock_descriptor, acquired = _try_probe_lock(paths.state_dir, harness)
    if not acquired:
        return _handle_unacquired_probe(
            paths, harness, expectations, clock, lock_descriptor
        )
    try:
        report = _run_probe(
            harness,
            paths,
            expectations,
            timeout_seconds,
            environment,
            inventory_observed,
            observed_servers,
            runner,
            clock,
        )
        if not _atomic_write_report(_cache_path(paths, harness), report):
            return _append_degraded_row(report, "__state__", "unavailable", clock)
        return report
    finally:
        _release_probe_lock(lock_descriptor)


def _handle_unacquired_probe(
    paths: RuntimePaths,
    harness: str,
    expectations: Expectations,
    clock: Clock,
    lock_descriptor: int | None,
) -> dict[str, Any]:
    try:
        cached = _fresh_cached_report(paths, harness, expectations, clock)
        if cached is not None:
            return cached
        if lock_descriptor is not None:
            return _not_probed_report(
                harness, expectations, clock, reason="probe_in_progress"
            )
        return _append_degraded_row(
            _not_probed_report(harness, expectations, clock),
            "__state__",
            "unavailable",
            clock,
        )
    finally:
        _release_probe_lock(lock_descriptor)


def _run_probe(
    harness: str,
    paths: RuntimePaths,
    expectations: Expectations,
    timeout_seconds: float,
    environment: Mapping[str, str],
    inventory_observed: bool,
    observed_servers: Sequence[str],
    runner: Runner,
    clock: Clock,
) -> dict[str, Any]:
    if harness == "claude":
        return probe_claude(
            paths, expectations, timeout_seconds, environment, runner, clock
        )
    return probe_omp(
        expectations,
        inventory_observed=inventory_observed,
        observed_servers=observed_servers,
        clock=clock,
    )


def _positive_capped_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return min(parsed, MAX_TIMEOUT_SECONDS)


def render_text(report: Mapping[str, Any]) -> str:
    if report.get("status") == "ok":
        return "MCP health: ok"
    reasons = sorted(
        {
            str(item.get("reason_code"))
            for item in report.get("servers", [])
            if isinstance(item, dict) and item.get("status") == "degraded"
        }
    )
    summary = ",".join(reasons[:3]) if reasons else "unavailable"
    return f"MCP health: degraded ({summary[:120]})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit sanitized JSON")
    parser.add_argument(
        "--probe", action="store_true", help="force a fresh observation"
    )
    parser.add_argument("--harness", required=True, choices=("claude", "omp"))
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_capped_timeout,
        default=MAX_TIMEOUT_SECONDS,
    )
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument(
        "--inventory-observed", action="store_true", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--observed-server",
        action="append",
        default=[],
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.harness != "omp" and (args.inventory_observed or args.observed_server):
        parser.error("OMP inventory arguments require --harness omp")
    environment = dict(os.environ)
    paths = RuntimePaths.from_environment(environment, args.state_dir)
    report = collect_health(
        harness=args.harness,
        probe=args.probe,
        timeout_seconds=args.timeout_seconds,
        paths=paths,
        environment=environment,
        inventory_observed=args.inventory_observed,
        observed_servers=args.observed_server,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
