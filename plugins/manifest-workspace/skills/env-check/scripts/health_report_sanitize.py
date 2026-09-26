"""Sanitizers for external health probe documents."""
# ruff: noqa: F405

from __future__ import annotations

from health_report_common import *  # noqa: F403


def _json_command_document(result: CommandResult) -> dict[str, Any] | None:
    if result.outcome != "complete":
        return None
    try:
        value = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _safe_reason(value: object) -> bool:
    return isinstance(value, str) and SAFE_CODE.fullmatch(value) is not None


def _sanitize_mcp(
    result: CommandResult,
    harness: str,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    if result.outcome != "complete":
        code = "mcp_timeout" if result.outcome == "timeout" else "mcp_unavailable"
        _add_finding(findings, code, "mcp", harness)
        return {"status": "degraded", "servers": []}
    document = _json_command_document(result)
    valid = (
        document is not None
        and set(document)
        == {"schema_version", "observed_at", "harness", "status", "servers"}
        and document.get("schema_version") == 1
        and document.get("harness") == harness
        and document.get("status") in {"ok", "degraded"}
        and isinstance(document.get("observed_at"), str)
        and isinstance(document.get("servers"), list)
        and len(document["servers"]) <= 1000
    )
    servers: list[dict[str, str]] = []
    if valid:
        for row in document["servers"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"name", "status", "reason_code"}
                or not isinstance(row.get("name"), str)
                or SAFE_NAME.fullmatch(row["name"]) is None
                or row.get("status") not in VALID_MCP_STATUSES
                or row.get("reason_code") not in VALID_MCP_REASONS
            ):
                valid = False
                break
            servers.append(
                {
                    "name": row["name"],
                    "status": row["status"],
                    "reason_code": row["reason_code"],
                }
            )
    expected_rc = 0 if valid and document and document["status"] == "ok" else 1
    if not valid or result.returncode != expected_rc:
        _add_finding(findings, "mcp_unparseable", "mcp", harness)
        return {"status": "degraded", "servers": []}
    assert document is not None
    if document["status"] != "ok":
        _add_finding(findings, "mcp_degraded", "mcp", harness)
    return {
        "status": document["status"],
        "observed_at": document["observed_at"],
        "servers": sorted(servers, key=lambda item: item["name"]),
    }


def _parse_hook_document(
    result: CommandResult,
) -> tuple[dict[str, Any], dict[str, str], list[dict[str, str]], list[str]] | None:
    if result.outcome != "complete":
        return None
    document = _json_command_document(result)
    valid = (
        document is not None
        and set(document)
        == {"schema_version", "observed_at", "status", "hashes", "checks", "findings"}
        and document.get("schema_version") == 1
        and document.get("status") in {"ok", "degraded"}
        and isinstance(document.get("observed_at"), str)
        and isinstance(document.get("hashes"), dict)
        and isinstance(document.get("checks"), list)
        and isinstance(document.get("findings"), list)
    )
    if not valid:
        return None
    hashes: dict[str, str] = {}
    for name, digest in document["hashes"].items():
        if (
            not isinstance(name, str)
            or not SAFE_NAME.fullmatch(name)
            or not isinstance(digest, str)
            or not SHA256.fullmatch(digest)
        ):
            return None
        hashes[name] = digest
    checks: list[dict[str, str]] = []
    for row in document["checks"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"name", "status", "reason_code"}
            or not isinstance(row.get("name"), str)
            or not SAFE_NAME.fullmatch(row["name"])
            or row.get("status") not in {"ok", "degraded"}
            or not _safe_reason(row.get("reason_code"))
        ):
            return None
        checks.append(dict(row))
    reasons: list[str] = []
    for reason in document["findings"]:
        if not _safe_reason(reason):
            return None
        reasons.append(reason)
    return document, hashes, checks, reasons


def _sanitize_hook(
    result: CommandResult,
    baseline_hashes: object,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    if result.outcome != "complete":
        code = "hook_timeout" if result.outcome == "timeout" else "hook_unavailable"
        _add_finding(findings, code, "hooks", "claude")
        return {"status": "degraded", "hashes": {}, "checks": [], "findings": [code]}
    parsed = _parse_hook_document(result)
    if parsed is None:
        _add_finding(findings, "hook_unparseable", "hooks", "claude")
        return {
            "status": "degraded",
            "hashes": {},
            "checks": [],
            "findings": ["hook_unparseable"],
        }
    document, hashes, checks, reason_codes = parsed
    if result.returncode != (0 if document["status"] == "ok" else 1):
        _add_finding(findings, "hook_unparseable", "hooks", "claude")
        return {
            "status": "degraded",
            "hashes": {},
            "checks": [],
            "findings": ["hook_unparseable"],
        }
    if not isinstance(baseline_hashes, dict) or not baseline_hashes:
        _add_finding(findings, "hook_baseline_missing", "hooks", "claude")
    elif baseline_hashes != hashes:
        _add_finding(findings, "hook_hash_changed", "hooks", "claude")
    assert document is not None
    if document["status"] != "ok":
        _add_finding(findings, "hook_degraded", "hooks", "claude")
    return {
        "status": document["status"],
        "observed_at": document["observed_at"],
        "hashes": dict(sorted(hashes.items())),
        "checks": checks,
        "findings": sorted(set(reason_codes)),
    }


def _extract_version(output: str) -> str | None:
    first = output.strip().splitlines()[0] if output.strip() else ""
    match = VERSION.search(first[:256])
    return match.group(1) if match else None


def _sanitize_inventory(
    result: CommandResult,
    receipt: dict[str, Any] | None,
    harness_names: Sequence[str],
    findings: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    summaries = {
        name: {"status": "degraded", "state": "unavailable"} for name in harness_names
    }
    if result.outcome != "complete":
        code = (
            "inventory_timeout"
            if result.outcome == "timeout"
            else "inventory_unavailable"
        )
        for name in harness_names:
            _add_finding(findings, code, "inventory", name)
        return summaries
    document = _json_command_document(result)
    rows = document.get("harnesses") if document else None
    if not isinstance(rows, dict):
        for name in harness_names:
            _add_finding(findings, "inventory_unparseable", "inventory", name)
        return summaries
    receipt_harnesses = receipt.get("harnesses", {}) if receipt else {}
    for name in harness_names:
        row = rows.get(name)
        if not isinstance(row, dict):
            _add_finding(findings, "inventory_missing", "inventory", name)
            continue
        state = row.get("state")
        plugin_ids = row.get("installed_plugin_ids")
        capabilities = row.get("capabilities")
        if (
            state not in {"READY", "DEGRADED", "DRIFTED", "BLOCKED"}
            or _normalized_plugins(plugin_ids) is None
            or not _valid_string_map(capabilities)
        ):
            _add_finding(findings, "inventory_unparseable", "inventory", name)
            continue
        status = "ok" if state == "READY" else "degraded"
        summaries[name] = {"status": status, "state": state}
        if state != "READY":
            _add_finding(findings, "inventory_degraded", "inventory", name)
        prior = receipt_harnesses.get(name)
        if isinstance(prior, dict):
            observed_plugins = _normalized_plugins(plugin_ids)
            recorded_plugins = _normalized_plugins(prior.get("plugin_ids"))
            if observed_plugins != recorded_plugins:
                _add_finding(findings, "inventory_drift", "inventory", name)
            for identity, recorded_state in prior.get("capabilities", {}).items():
                observed_state = capabilities.get(identity)
                if observed_state is None or _capability_is_bad(str(observed_state)):
                    _add_finding(findings, "capability_drift", "inventory", name)
                elif _capability_is_bad(str(recorded_state)):
                    _add_finding(findings, "capability_blocked", "inventory", name)
    return summaries


def _status_for_harness(findings: Sequence[Mapping[str, str]], harness: str) -> str:
    return (
        "degraded" if any(item.get("harness") == harness for item in findings) else "ok"
    )
