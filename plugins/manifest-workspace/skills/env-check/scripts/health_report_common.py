"""Internal helpers for the health report collector."""
# ruff: noqa: F401, E402, I001

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
from contextlib import suppress
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
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
        "health_report_collect.py",
        "health_report_common.py",
        "health_report_inspect.py",
        "health_report_sanitize.py",
        "mcp_health.py",
        "mcp_health_expectations.py",
        "mcp_health_report.py",
        "mcp_health_runtime.py",
        "health_install_files.py",
        "health_install_reconcile.py",
        "env_check.py",
        "hook_smoke.py",
        "hook_smoke_support.py",
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
    return datetime.now(UTC)


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (
        moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError, OSError):
        with suppress(OSError):
            process.kill()


def run_bounded(
    argv: Sequence[str],
    timeout_seconds: float,
    environment: Mapping[str, str],
) -> CommandResult:
    """Run one argv-only child, bounding output and its whole process group."""
    if not argv or timeout_seconds <= 0:
        return CommandResult("timeout")
    with (
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
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
    return Path(environment.get("XDG_STATE_HOME") or home / ".local/state").expanduser()


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
        if not any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            return None
        if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
            return value
        return None
    return None


def _canonical_bundles(
    source_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    contracts = source_root / "src" / ("manifest" + "_agent") / "contracts.py"
    try:
        tree = ast.parse(contracts.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return None
    domain = _literal_tuple_assignment(tree, "DOMAIN_BUNDLES")
    addons = _literal_tuple_assignment(tree, "ADDON_BUNDLES")
    if domain is None or addons is None or not domain:
        return None
    if len({*domain, *addons}) != len((*domain, *addons)):
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


__all__ = [name for name in globals() if not name.startswith("__")]
