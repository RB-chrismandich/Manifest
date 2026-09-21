#!/usr/bin/env python3
"""Produce a bounded, local, sanitized weekly harness health report."""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
REPORT_SECONDS = 60.0
OBSERVATION_SECONDS = 58.0
MAX_CAPTURE_BYTES = 1024 * 1024
MAX_WORKERS = 4
NESTED_PROBE_CLEANUP_SECONDS = 1.5
MAX_RECEIPT_AGE_SECONDS = 7 * 24 * 60 * 60
WEEKLY_RETENTION = 12
COORDINATOR_HARNESSES = frozenset(
    {"claude", "codex", "gemini", "cursor", "antigravity", "devin"}
)
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:@+-]{1,240}$")
SAFE_CODE = re.compile(r"^[a-z][a-z0-9_.:-]{0,119}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"(?<![0-9])([0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9.-]+)?)")
WEEKLY_FILE = re.compile(r"^weekly-[0-9]{8}\.json$")
BAD_CAPABILITY_STATES = frozenset(
    {
        "absent",
        "blocked",
        "degraded",
        "drifted",
        "error",
        "failed",
        "missing",
        "unavailable",
        "unsupported",
        "unverified",
    }
)
EXPECTED_RUNTIME_FILES = frozenset(
    {
        "health_report.py",
        "mcp_health.py",
        "env_check.py",
        "plugin_reconcile.py",
        "hook_smoke.py",
    }
)
VALID_MCP_STATUSES = frozenset({"healthy", "disabled", "degraded"})
VALID_MCP_REASONS = frozenset(
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


@dataclass(frozen=True)
class CommandResult:
    outcome: str
    returncode: int | None = None
    stdout: str = ""


@dataclass(frozen=True)
class Observation:
    key: str
    kind: str
    harness: str | None
    argv: tuple[str, ...]
    limit_seconds: float


Runner = Callable[[Sequence[str], float, Mapping[str, str]], CommandResult]
Clock = Callable[[], datetime]
Monotonic = Callable[[], float]
PackageVersion = Callable[[str], str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (
        moment.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def run_bounded(
    argv: Sequence[str],
    timeout_seconds: float,
    environment: Mapping[str, str],
) -> CommandResult:
    """Run one argv-only child, bounding output and its whole process group."""
    if not argv or timeout_seconds <= 0:
        return CommandResult("timeout")
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                [str(item) for item in argv],
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except (OSError, ValueError):
            return CommandResult("unavailable")
        try:
            process.wait(timeout=max(0.01, timeout_seconds))
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            try:
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                _kill_process_group(process)
            return CommandResult("timeout")
        stdout_file.seek(0)
        payload = stdout_file.read(MAX_CAPTURE_BYTES + 1)
        if len(payload) > MAX_CAPTURE_BYTES:
            return CommandResult("unparseable", process.returncode)
        try:
            output = payload.decode("utf-8")
        except UnicodeDecodeError:
            return CommandResult("unparseable", process.returncode)
        return CommandResult("complete", process.returncode, output)


def _state_home(environment: Mapping[str, str]) -> Path:
    home = Path(environment.get("HOME") or Path.home()).expanduser()
    return Path(
        environment.get("XDG_STATE_HOME") or home / ".local/state"
    ).expanduser()


def _agent_root(environment: Mapping[str, str]) -> Path:
    home = Path(environment.get("HOME") or Path.home()).expanduser()
    return Path(
        environment.get("PI_CODING_AGENT_DIR")
        or environment.get("OMP_AGENT_DIR")
        or home / ".omp/agent"
    ).expanduser()


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_CAPTURE_BYTES + 1)
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "unavailable"
    if len(payload) > MAX_CAPTURE_BYTES:
        return None, "unparseable"
    try:
        return json.loads(payload.decode("utf-8")), None
    except (UnicodeError, json.JSONDecodeError):
        return None, "unparseable"


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _safe_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
    except OSError:
        return False


def _finding(
    code: str,
    component: str,
    harness: str | None = None,
) -> dict[str, str]:
    row = {"code": code, "component": component}
    if harness is not None:
        row["harness"] = harness
    return row


def _add_finding(
    findings: list[dict[str, str]],
    code: str,
    component: str,
    harness: str | None = None,
) -> None:
    row = _finding(code, component, harness)
    if row not in findings:
        findings.append(row)


def _valid_string_map(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _valid_receipt(value: object) -> bool:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return False
    required_strings = (
        "coordinator_version",
        "release_version",
        "source_commit",
        "archive_sha256",
    )
    if any(not isinstance(value.get(key), str) for key in required_strings):
        return False
    if not isinstance(value.get("source_dirty"), bool):
        return False
    if not _valid_string_map(value.get("bundle_checksums")):
        return False
    if not isinstance(value.get("selected_optional"), list) or not all(
        isinstance(item, str) for item in value["selected_optional"]
    ):
        return False
    harnesses = value.get("harnesses")
    if not isinstance(harnesses, dict):
        return False
    for name, record in harnesses.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            return False
        if record.get("harness") != name:
            return False
        if any(
            not isinstance(record.get(key), str)
            for key in ("adapter_version", "native_version")
        ):
            return False
        if not isinstance(record.get("verified"), bool):
            return False
        if not isinstance(record.get("plugin_ids"), list) or not all(
            isinstance(item, str) for item in record["plugin_ids"]
        ):
            return False
        if not _valid_string_map(record.get("capabilities")):
            return False
        if not isinstance(record.get("errors"), list) or not all(
            isinstance(item, str) for item in record["errors"]
        ):
            return False
        if not isinstance(record.get("owned_entries"), list):
            return False
    return True


def _load_coordinator_receipt(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Reuse env-check's receipt reader when installed beside this script."""
    try:
        import env_check  # type: ignore[import-not-found]

        document, error = env_check.load_receipt(path)
    except (ImportError, AttributeError, OSError, ValueError):
        document, error = _read_json(path)
        if error == "missing":
            error = "installation receipt is absent"
        elif error is not None:
            error = "installation receipt is unreadable"
    if error is not None or not _valid_receipt(document):
        return None, "missing" if not path.exists() else "malformed"
    return document, None


def _literal_tuple_assignment(tree: ast.AST, name: str) -> tuple[str, ...] | None:
    for node in getattr(tree, "body", ()):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            return None
        if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
            return value
        return None
    return None


def _canonical_bundles(source_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    contracts = source_root / "src" / ("manifest" + "_agent") / "contracts.py"
    try:
        tree = ast.parse(contracts.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return None
    domain = _literal_tuple_assignment(tree, "DOMAIN_BUNDLES")
    addons = _literal_tuple_assignment(tree, "ADDON_BUNDLES")
    if domain is None or addons is None or not domain:
        return None
    if len(set((*domain, *addons))) != len((*domain, *addons)):
        return None
    return domain, addons


def _yaml_inline_list(value: str) -> tuple[str, ...] | None:
    value = value.strip()
    if not value.startswith("[") or not value.endswith("]"):
        return None
    body = value[1:-1].strip()
    if not body:
        return ()
    items: list[str] = []
    for raw in body.split(","):
        item = raw.strip().strip("'\"")
        if not SAFE_NAME.fullmatch(item):
            return None
        items.append(item)
    return tuple(items)


def _contract_expectations(
    source_root: Path,
    bundle: str,
    selected_optional: set[str],
) -> set[str] | None:
    path = source_root / "plugins" / bundle / "manifest-capabilities.yml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    declared_name: str | None = None
    in_bundle = False
    in_capabilities = False
    capability_kind: str | None = None
    expected: set[str] = set()
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "bundle:" and indent == 0:
            in_bundle = True
            in_capabilities = False
            capability_kind = None
            continue
        if stripped == "capabilities:" and indent == 0:
            in_bundle = False
            in_capabilities = True
            capability_kind = None
            continue
        if indent == 0 and stripped.endswith(":"):
            if stripped not in {"bundle:", "capabilities:"}:
                in_bundle = False
                in_capabilities = False
                capability_kind = None
            continue
        if in_bundle and indent == 2 and stripped.startswith("name:"):
            declared_name = stripped.partition(":")[2].strip().strip("'\"")
            continue
        if in_capabilities and indent == 2 and stripped in {"mcp:", "executables:"}:
            capability_kind = "mcp" if stripped == "mcp:" else "executable"
            continue
        if in_capabilities and capability_kind and indent == 4 and ":" in stripped:
            tier, _separator, raw_values = stripped.partition(":")
            if tier not in {"required", "default", "optional"}:
                continue
            values = _yaml_inline_list(raw_values)
            if values is None:
                return None
            for item in values:
                identity = f"{bundle}:{capability_kind}:{item}"
                if tier != "optional" or (
                    item in selected_optional
                    or f"{capability_kind}:{item}" in selected_optional
                    or identity in selected_optional
                ):
                    expected.add(identity)
    if declared_name != bundle:
        return None
    return expected


def _normalized_plugins(values: object) -> set[str] | None:
    if not isinstance(values, list):
        return None
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            return None
        name = value.split("@", 1)[0]
        if not SAFE_NAME.fullmatch(name):
            return None
        normalized.add(name)
    return normalized


def _capability_is_bad(value: str) -> bool:
    normalized = value.strip().lower().replace(" ", "_")
    return normalized in BAD_CAPABILITY_STATES or any(
        token in BAD_CAPABILITY_STATES
        for token in re.split(r"[^a-z]+", normalized)
        if token
    )


def _inspect_receipt(
    receipt_path: Path,
    source_root: Path | None,
    requested: Sequence[str],
    now: datetime,
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any] | None, tuple[str, ...]]:
    document, error = _load_coordinator_receipt(receipt_path)
    summary: dict[str, Any] = {
        "status": "ok",
        "present": document is not None,
        "age_days": None,
        "release_version": None,
        "source_dirty": None,
        "installation": "unknown",
    }
    if error:
        code = "receipt_missing" if error == "missing" else "receipt_malformed"
        _add_finding(findings, code, "receipt")
        summary["status"] = "degraded"
        return summary, None, ()
    assert document is not None
    try:
        modified = datetime.fromtimestamp(receipt_path.stat().st_mtime, timezone.utc)
        age = (now.astimezone(timezone.utc) - modified).total_seconds()
    except (OSError, OverflowError, ValueError):
        age = MAX_RECEIPT_AGE_SECONDS + 1
        _add_finding(findings, "receipt_unavailable", "receipt")
    summary["age_days"] = round(max(0.0, age) / 86400, 2)
    summary["release_version"] = document["release_version"]
    summary["source_dirty"] = document["source_dirty"]
    if age > MAX_RECEIPT_AGE_SECONDS:
        _add_finding(findings, "receipt_stale", "receipt")
    if age < -300:
        _add_finding(findings, "receipt_future", "receipt")

    bundles = _canonical_bundles(source_root) if source_root is not None else None
    expected_bundles: tuple[str, ...] = ()
    expectations: dict[str, set[str]] = {}
    if bundles is None:
        _add_finding(findings, "contract_catalog_unavailable", "receipt")
    else:
        expected_bundles, addons = bundles
        selected = set(document["selected_optional"])
        for bundle in (*expected_bundles, *addons):
            expected = _contract_expectations(source_root, bundle, selected)
            if expected is None:
                _add_finding(findings, "contract_unparseable", "receipt")
                continue
            expectations[bundle] = expected

    harnesses = document["harnesses"]
    for harness, record in sorted(harnesses.items()):
        if not record["verified"]:
            _add_finding(findings, "harness_unverified", "receipt", harness)
        if record["errors"]:
            _add_finding(findings, "harness_receipt_error", "receipt", harness)
        installed = _normalized_plugins(record["plugin_ids"])
        if installed is None:
            _add_finding(findings, "inventory_unparseable", "receipt", harness)
            installed = set()
        for bundle in expected_bundles:
            if bundle not in installed:
                _add_finding(findings, "bundle_missing", "receipt", harness)
        capabilities = record["capabilities"]
        for identity, state in capabilities.items():
            if _capability_is_bad(state):
                _add_finding(findings, "capability_blocked", "receipt", harness)
        for bundle in installed:
            for identity in expectations.get(bundle, set()):
                if identity not in capabilities:
                    _add_finding(findings, "capability_missing", "receipt", harness)
    if "claude" in requested and "claude" not in harnesses:
        _add_finding(findings, "requested_harness_missing", "receipt", "claude")
    summary["status"] = (
        "degraded"
        if any(item["component"] == "receipt" for item in findings)
        else "ok"
    )
    return summary, document, expected_bundles


def _valid_owned_row(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = ("source", "destination", "source_sha256", "destination_sha256")
    return all(isinstance(value.get(key), str) for key in required) and all(
        SHA256.fullmatch(str(value[key]))
        for key in ("source_sha256", "destination_sha256")
    )


def _verify_owned_row(
    row: object,
    expected_destination: Path,
) -> bool:
    if not _valid_owned_row(row):
        return False
    assert isinstance(row, dict)
    destination = Path(row["destination"]).expanduser()
    try:
        if destination.resolve(strict=False) != expected_destination.resolve(strict=False):
            return False
    except OSError:
        return False
    observed = _sha256(destination) if _safe_regular_file(destination) else None
    return observed == row["destination_sha256"] == row["source_sha256"]


def _inspect_installation(
    environment: Mapping[str, str],
    runtime_dir: Path,
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any] | None, Path | None, dict[str, str]]:
    path = _state_home(environment) / "manifest/health/installation.json"
    value, error = _read_json(path)
    if error or not isinstance(value, dict) or value.get("schema_version") != 1:
        _add_finding(findings, "health_installation_missing", "installation")
        return None, None, {}
    source_value = value.get("source_root")
    executables = value.get("executables")
    files = value.get("files")
    if (
        not isinstance(source_value, str)
        or not Path(source_value).is_absolute()
        or not isinstance(executables, dict)
        or not isinstance(files, dict)
    ):
        _add_finding(findings, "health_installation_malformed", "installation")
        return None, None, {}
    clean_executables = {
        key: item
        for key, item in executables.items()
        if key in {"python", "omp", "claude", "coordinator"}
        and isinstance(item, str)
        and Path(item).is_absolute()
    }
    if set(clean_executables) != {"python", "omp", "claude", "coordinator"}:
        _add_finding(findings, "native_cli_missing", "installation")
    if set(files) != EXPECTED_RUNTIME_FILES:
        _add_finding(findings, "health_runtime_incomplete", "installation")
    for name in EXPECTED_RUNTIME_FILES:
        if not _verify_owned_row(files.get(name), runtime_dir / name):
            _add_finding(findings, "health_runtime_drift", "installation")
    agent_root = _agent_root(environment)
    if not _verify_owned_row(
        value.get("omp_extension"), agent_root / "extensions/manifest-health.ts"
    ):
        _add_finding(findings, "omp_extension_drift", "installation", "omp")
    home = Path(environment.get("HOME") or Path.home()).expanduser()
    if not _verify_owned_row(
        value.get("claude_wrapper"), home / ".claude/scripts/mcp_health_check.sh"
    ):
        _add_finding(findings, "claude_wrapper_drift", "installation", "claude")
    source_root = Path(source_value).expanduser()
    if not source_root.is_dir():
        _add_finding(findings, "source_root_unavailable", "installation")
        source_root = None
    return value, source_root, clean_executables


def _safe_pin_path(agent_root: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    candidate = agent_root.joinpath(*pure.parts)
    current = agent_root
    try:
        for part in pure.parts:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                return None
    except OSError:
        return None
    return candidate


def _inspect_pins(
    environment: Mapping[str, str],
    package_version: PackageVersion,
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, str]]:
    agent_root = _agent_root(environment)
    path = agent_root / "ui-workflow/dependencies.lock.json"
    value, error = _read_json(path)
    summary: dict[str, Any] = {
        "status": "ok",
        "omp": "unknown",
        "python": "unknown",
        "packages": {},
        "owned_files": {"checked": 0, "drifted": 0},
    }
    if error or not isinstance(value, dict) or value.get("schema_version") != 1:
        _add_finding(findings, "pin_manifest_unavailable", "pins")
        summary["status"] = "degraded"
        return summary, {}
    omp_pin = value.get("omp_version")
    python_pin = value.get("python_version")
    packages = value.get("python_packages")
    owned = value.get("owned_files")
    if (
        not isinstance(omp_pin, str)
        or not isinstance(python_pin, str)
        or not _valid_string_map(packages)
        or not _valid_string_map(owned)
    ):
        _add_finding(findings, "pin_manifest_malformed", "pins")
        summary["status"] = "degraded"
        return summary, {}
    summary["omp"] = omp_pin
    summary["python"] = python_pin
    if platform.python_version() != python_pin:
        _add_finding(findings, "python_pin_mismatch", "pins")
    for name, expected in sorted(packages.items()):
        if name not in {"PyYAML", "jsonschema"}:
            _add_finding(findings, "pin_manifest_malformed", "pins")
            continue
        try:
            observed = package_version(name)
        except Exception:
            observed = None
        matched = observed == expected
        summary["packages"][name] = "matched" if matched else "mismatched"
        if not matched:
            _add_finding(findings, "package_pin_mismatch", "pins")
    drifted = 0
    checked = 0
    for relative, expected in sorted(owned.items()):
        checked += 1
        target = _safe_pin_path(agent_root, relative)
        observed = _sha256(target) if target is not None and _safe_regular_file(target) else None
        if not SHA256.fullmatch(expected) or observed != expected:
            drifted += 1
            _add_finding(findings, "pin_hash_mismatch", "pins", "omp")
    summary["owned_files"] = {"checked": checked, "drifted": drifted}
    summary["status"] = (
        "degraded" if any(item["component"] == "pins" for item in findings) else "ok"
    )
    return summary, {"omp": omp_pin, "python": python_pin}


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
        and set(document) == {"schema_version", "observed_at", "harness", "status", "servers"}
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


def _sanitize_hook(
    result: CommandResult,
    baseline_hashes: object,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    if result.outcome != "complete":
        code = "hook_timeout" if result.outcome == "timeout" else "hook_unavailable"
        _add_finding(findings, code, "hooks", "claude")
        return {"status": "degraded", "hashes": {}, "checks": [], "findings": [code]}
    document = _json_command_document(result)
    valid = (
        document is not None
        and set(document) == {
            "schema_version",
            "observed_at",
            "status",
            "hashes",
            "checks",
            "findings",
        }
        and document.get("schema_version") == 1
        and document.get("status") in {"ok", "degraded"}
        and isinstance(document.get("observed_at"), str)
        and isinstance(document.get("hashes"), dict)
        and isinstance(document.get("checks"), list)
        and isinstance(document.get("findings"), list)
    )
    hashes: dict[str, str] = {}
    checks: list[dict[str, str]] = []
    reason_codes: list[str] = []
    if valid:
        for name, digest in document["hashes"].items():
            if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
                valid = False
                break
            hashes[name] = digest
    if valid:
        for row in document["checks"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"name", "status", "reason_code"}
                or not isinstance(row.get("name"), str)
                or not SAFE_NAME.fullmatch(row["name"])
                or row.get("status") not in {"ok", "degraded"}
                or not _safe_reason(row.get("reason_code"))
            ):
                valid = False
                break
            checks.append(dict(row))
    if valid:
        for reason in document["findings"]:
            if not _safe_reason(reason):
                valid = False
                break
            reason_codes.append(reason)
    expected_rc = 0 if valid and document and document["status"] == "ok" else 1
    if not valid or result.returncode != expected_rc:
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
        name: {"status": "degraded", "state": "unavailable"}
        for name in harness_names
    }
    if result.outcome != "complete":
        code = "inventory_timeout" if result.outcome == "timeout" else "inventory_unavailable"
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
    return "degraded" if any(item.get("harness") == harness for item in findings) else "ok"


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

    python = executables.get("python")
    observations: list[Observation] = []
    if python:
        for harness in requested:
            helper = runtime_dir / "mcp_health.py"
            arguments = [python, str(helper), "--json", "--harness", harness]
            if harness == "claude":
                arguments.append("--probe")
            arguments.extend(
                ["--timeout-seconds", "20", "--state-dir", str(_state_home(environment) / "manifest/health")]
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
    else:
        for harness in requested:
            _add_finding(findings, "health_python_missing", "installation", harness)

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

    results = _collect_observations(
        observations,
        observation_deadline,
        monotonic,
        runner,
        environment,
    )

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
        else {name: {"status": "degraded", "state": "unavailable"} for name in coordinator_names}
    )

    harness_summary: dict[str, Any] = {}
    all_harnesses = sorted(set(requested) | set(receipt.get("harnesses", {}) if receipt else {}))
    for harness in all_harnesses:
        requested_harness = harness in requested
        version_result = results.get(f"version:{harness}") if requested_harness else None
        receipt_record = (
            receipt.get("harnesses", {}).get(harness)
            if receipt is not None
            else None
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
                        _add_finding(findings, "native_version_drift", "version", harness)
                        version_status = "degraded"
                    else:
                        version_status = "ok"
        inventory = inventories.get(harness)
        inventory_status = (
            inventory["status"]
            if inventory is not None
            else ("native" if harness == "omp" else "not_observed")
        )
        harness_summary[harness] = {
            "status": "ok",
            "requested": requested_harness,
            "version": observed_version,
            "version_status": version_status,
            "inventory_status": inventory_status,
        }

    findings.sort(key=lambda item: (item["component"], item.get("harness", ""), item["code"]))
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


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary: str | None = None
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        os.chmod(path, 0o600)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def write_reports(report: Mapping[str, Any], out_dir: Path) -> None:
    """Atomically write latest plus the UTC weekly file and retain twelve."""
    generated = report.get("generated_at")
    if not isinstance(generated, str) or len(generated) < 10:
        raise ValueError("report timestamp is invalid")
    day = generated[:10].replace("-", "")
    if not re.fullmatch(r"[0-9]{8}", day):
        raise ValueError("report timestamp is invalid")
    payload = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    weekly_path = out_dir / f"weekly-{day}.json"
    latest_path = out_dir / "latest.json"
    _atomic_write_bytes(weekly_path, payload)
    _atomic_write_bytes(latest_path, payload)
    completed = sorted(
        (
            path
            for path in out_dir.iterdir()
            if WEEKLY_FILE.fullmatch(path.name) and _safe_regular_file(path)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for expired in completed[WEEKLY_RETENTION:]:
        expired.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the sanitized report")
    parser.add_argument(
        "--harness",
        action="append",
        required=True,
        choices=("claude", "omp"),
        help="requested native harness; repeat for more than one",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def _render_text(report: Mapping[str, Any]) -> str:
    if report.get("status") == "ok":
        return "Weekly health: ok"
    findings = report.get("findings")
    codes = [
        str(item.get("code"))
        for item in findings[:3]
        if isinstance(item, dict) and _safe_reason(item.get("code"))
    ] if isinstance(findings, list) else []
    return f"Weekly health: degraded ({','.join(codes) or 'unavailable'})"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = collect_report(harnesses=args.harness)
    try:
        write_reports(report, args.out_dir.expanduser().resolve(strict=False))
    except (OSError, ValueError):
        findings = list(report["findings"])
        _add_finding(findings, "report_write_failed", "report")
        findings.sort(key=lambda item: (item["component"], item.get("harness", ""), item["code"]))
        report = {**report, "status": "degraded", "findings": findings}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
