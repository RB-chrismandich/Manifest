"""Report shaping, probe interpretation, and cache validation for MCP health."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_health_expectations import (
    INTERNAL_SERVER_NAMES,
    MAX_SERVER_COUNT,
    SERVER_NAME_RE,
    Expectations,
    RuntimePaths,
)
from mcp_health_runtime import (
    SCHEMA_VERSION,
    Clock,
    Runner,
    _read_json_object,
    _timestamp,
    utc_now,
)

MAX_CACHE_AGE_SECONDS = 5 * 60
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
VALID_STATUSES = frozenset({"healthy", "disabled", "degraded"})
VALID_REASONS = frozenset(
    {
        "connected",
        "auth_required",
        "connection_failed",
        "timeout",
        "unavailable",
        "unparseable",
        "not_probed",
        "probe_in_progress",
    }
)


def _row(name: str, status: str, reason_code: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason_code": reason_code}


def _configuration_row(expectations: Expectations) -> dict[str, str] | None:
    if not expectations.errors:
        return None
    reason = "unparseable" if "unparseable" in expectations.errors else "unavailable"
    return _row("__configuration__", "degraded", reason)


def _parse_claude_status(output: str, name: str) -> tuple[str, str]:
    prefix = f"{name}:"
    matches: list[str] = []
    for raw_line in output.splitlines():
        line = ANSI_RE.sub("", raw_line).strip()
        if not line.startswith(prefix):
            continue
        remainder = line[len(prefix) :]
        if not remainder or not remainder[0].isspace():
            continue
        matches.append(line)
    if len(matches) != 1:
        return "degraded", "unavailable" if not matches else "unparseable"
    if " - " not in matches[0]:
        return "degraded", "unparseable"
    status_text = matches[0].rsplit(" - ", 1)[1].strip()
    lowered = status_text.casefold()
    if re.fullmatch(r"(?:✔|✓)\s*connected", status_text, flags=re.IGNORECASE):
        return "healthy", "connected"
    if any(
        marker in lowered
        for marker in (
            "authentication required",
            "auth required",
            "needs authentication",
            "not authenticated",
            "incompatible auth",
        )
    ):
        return "degraded", "auth_required"
    if "timed out" in lowered or "timeout" in lowered:
        return "degraded", "timeout"
    if any(
        marker in lowered
        for marker in (
            "failed to connect",
            "connection failed",
            "connection closed",
            "disconnected",
        )
    ):
        return "degraded", "connection_failed"
    if "unavailable" in lowered or "not found" in lowered:
        return "degraded", "unavailable"
    return "degraded", "unparseable"


def _base_rows(expectations: Expectations) -> list[dict[str, str]]:
    return [
        _row(name, "disabled", "not_probed")
        for name, disabled in sorted(expectations.disabled.items())
        if disabled
    ]


def _report(
    harness: str,
    observed_at: datetime,
    rows: Sequence[dict[str, str]],
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda item: item["name"])
    status = (
        "degraded" if any(item["status"] == "degraded" for item in ordered) else "ok"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": _timestamp(observed_at),
        "harness": harness,
        "status": status,
        "servers": ordered,
    }


def probe_claude(
    paths: RuntimePaths,
    expectations: Expectations,
    timeout_seconds: float,
    environment: Mapping[str, str],
    runner: Runner,
    clock: Clock,
) -> dict[str, Any]:
    del paths
    rows = _base_rows(expectations)
    enabled = sorted(
        name for name, disabled in expectations.disabled.items() if not disabled
    )
    child_environment = dict(environment)
    child_environment.pop("CLAUDECODE", None)
    result = runner(
        ["claude", "mcp", "list"],
        timeout_seconds,
        child_environment,
    )
    failure_targets = enabled or ["__observation__"]
    if result.outcome == "timeout":
        rows.extend(_row(name, "degraded", "timeout") for name in failure_targets)
    elif result.outcome in {"overflow", "unparseable"}:
        rows.extend(_row(name, "degraded", "unparseable") for name in failure_targets)
    elif result.outcome != "completed" or result.returncode != 0:
        rows.extend(_row(name, "degraded", "unavailable") for name in failure_targets)
    elif not result.output.strip():
        rows.extend(_row(name, "degraded", "unparseable") for name in failure_targets)
    else:
        for name in enabled:
            status, reason = _parse_claude_status(result.output, name)
            rows.append(_row(name, status, reason))
    config_row = _configuration_row(expectations)
    if config_row:
        rows.append(config_row)
    return _report("claude", clock(), rows)


def probe_omp(
    expectations: Expectations,
    *,
    inventory_observed: bool,
    observed_servers: Sequence[str],
    clock: Clock,
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    valid_observed: set[str] = set()
    invalid_observation = len(observed_servers) > MAX_SERVER_COUNT
    for name in observed_servers[:MAX_SERVER_COUNT]:
        if SERVER_NAME_RE.fullmatch(name) and name not in INTERNAL_SERVER_NAMES:
            valid_observed.add(name)
        else:
            invalid_observation = True

    if inventory_observed:
        for name, disabled in sorted(expectations.disabled.items()):
            if disabled:
                if name in valid_observed:
                    rows.append(_row(name, "degraded", "unparseable"))
                else:
                    rows.append(_row(name, "disabled", "not_probed"))
            elif name in valid_observed:
                rows.append(_row(name, "healthy", "connected"))
            else:
                rows.append(_row(name, "degraded", "unavailable"))
        expected_names = set(expectations.disabled)
        rows.extend(
            _row(name, "degraded", "unparseable")
            for name in sorted(valid_observed - expected_names)
        )
        if invalid_observation:
            rows.append(_row("__inventory__", "degraded", "unparseable"))
    else:
        rows.extend(
            _row(name, "disabled", "not_probed")
            if disabled
            else _row(name, "degraded", "unavailable")
            for name, disabled in sorted(expectations.disabled.items())
        )
        rows.append(_row("__inventory__", "degraded", "unavailable"))

    config_row = _configuration_row(expectations)
    if config_row:
        rows.append(config_row)
    return _report("omp", clock(), rows)


def _parse_cached_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _validated_cached_report(
    path: Path,
    harness: str,
    now: datetime,
) -> dict[str, Any] | None:
    cached, error = _read_json_object(path, required=False)
    if error or cached is None:
        return None
    if (
        cached.get("schema_version") != SCHEMA_VERSION
        or cached.get("harness") != harness
        or cached.get("status") not in {"ok", "degraded"}
    ):
        return None
    observed_at = _parse_cached_timestamp(cached.get("observed_at"))
    if observed_at is None:
        return None
    current = now.astimezone(UTC)
    age = (current - observed_at).total_seconds()
    if age < -60 or age >= MAX_CACHE_AGE_SECONDS:
        return None
    servers = cached.get("servers")
    if not isinstance(servers, list) or len(servers) > MAX_SERVER_COUNT:
        return None
    clean_servers: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for item in servers:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        status = item.get("status")
        reason = item.get("reason_code")
        if (
            not isinstance(name, str)
            or not SERVER_NAME_RE.fullmatch(name)
            or name in seen_names
            or status not in VALID_STATUSES
            or reason not in VALID_REASONS
            or (status == "healthy" and reason != "connected")
            or (status == "disabled" and reason != "not_probed")
            or (status == "degraded" and reason == "connected")
        ):
            return None
        seen_names.add(name)
        clean_servers.append(_row(name, status, reason))
    derived_status = (
        "degraded"
        if any(item["status"] == "degraded" for item in clean_servers)
        else "ok"
    )
    if cached["status"] != derived_status:
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": _timestamp(observed_at),
        "harness": harness,
        "status": derived_status,
        "servers": clean_servers,
    }


def _reconcile_cached(
    cached: dict[str, Any],
    harness: str,
    expectations: Expectations,
) -> dict[str, Any]:
    cached_by_name = {item["name"]: item for item in cached["servers"]}
    rows: list[dict[str, str]] = []
    for name, disabled in sorted(expectations.disabled.items()):
        prior = cached_by_name.get(name)
        if disabled:
            if (
                prior is not None
                and prior["status"] == "degraded"
                and prior["reason_code"] == "unparseable"
            ):
                rows.append(dict(prior))
            else:
                rows.append(_row(name, "disabled", "not_probed"))
            continue
        if prior is None or prior["status"] == "disabled":
            rows.append(_row(name, "degraded", "not_probed"))
        else:
            rows.append(dict(prior))

    if "__observation__" in cached_by_name:
        rows.append(dict(cached_by_name["__observation__"]))
    if harness == "omp":
        if "__inventory__" in cached_by_name:
            rows.append(dict(cached_by_name["__inventory__"]))
        expected_names = set(expectations.disabled)
        rows.extend(
            dict(item)
            for name, item in sorted(cached_by_name.items())
            if not name.startswith("__") and name not in expected_names
        )
    config_row = _configuration_row(expectations)
    if config_row:
        rows.append(config_row)
    return _report(
        harness,
        _parse_cached_timestamp(cached["observed_at"]) or utc_now(),
        rows,
    )


def _not_probed_report(
    harness: str,
    expectations: Expectations,
    clock: Clock,
    *,
    reason: str = "not_probed",
) -> dict[str, Any]:
    rows = _base_rows(expectations)
    rows.extend(
        _row(name, "degraded", reason)
        for name, disabled in sorted(expectations.disabled.items())
        if not disabled
    )
    config_row = _configuration_row(expectations)
    if config_row:
        rows.append(config_row)
    if reason == "probe_in_progress":
        rows.append(_row("__probe__", "degraded", reason))
    elif harness == "omp":
        rows.append(_row("__inventory__", "degraded", "not_probed"))
    return _report(harness, clock(), rows)


def _cache_path(paths: RuntimePaths, harness: str) -> Path:
    return paths.state_dir / f"mcp-{harness}.json"


def _fresh_cached_report(
    paths: RuntimePaths,
    harness: str,
    expectations: Expectations,
    clock: Clock,
) -> dict[str, Any] | None:
    cached = _validated_cached_report(_cache_path(paths, harness), harness, clock())
    if cached is None:
        return None
    return _reconcile_cached(cached, harness, expectations)


def _append_degraded_row(
    report: Mapping[str, Any],
    name: str,
    reason: str,
    clock: Clock,
) -> dict[str, Any]:
    rows = [dict(item) for item in report.get("servers", [])]
    rows = [item for item in rows if item.get("name") != name]
    rows.append(_row(name, "degraded", reason))
    return _report(str(report["harness"]), clock(), rows)
