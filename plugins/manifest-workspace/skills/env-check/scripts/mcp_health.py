#!/usr/bin/env python3
"""Observe configured MCP servers without persisting native command output."""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_CACHE_AGE_SECONDS = 5 * 60
MAX_SERVER_COUNT = 1000
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
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
INTERNAL_SERVER_NAMES = frozenset(
    {
        "__configuration__",
        "__inventory__",
        "__observation__",
        "__probe__",
        "__state__",
    }
)


@dataclass(frozen=True)
class RuntimePaths:
    home: Path
    state_dir: Path
    claude_config: Path
    claude_settings: Path
    plugin_index: Path
    omp_agent_dir: Path

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        state_dir: Path | None = None,
    ) -> "RuntimePaths":
        home = Path(environment.get("HOME") or Path.home()).expanduser()
        state_home = Path(
            environment.get("XDG_STATE_HOME") or home / ".local/state"
        ).expanduser()
        omp_agent = Path(
            environment.get("PI_CODING_AGENT_DIR")
            or environment.get("OMP_AGENT_DIR")
            or home / ".omp/agent"
        ).expanduser()
        return cls(
            home=home,
            state_dir=(state_dir or state_home / "manifest/health").expanduser(),
            claude_config=home / ".claude.json",
            claude_settings=home / ".claude/settings.json",
            plugin_index=home / ".claude/plugins/installed_plugins.json",
            omp_agent_dir=omp_agent,
        )


@dataclass
class Expectations:
    disabled: dict[str, bool] = field(default_factory=dict)
    errors: set[str] = field(default_factory=set)

    def add(self, name: object, *, disabled: bool, overwrite: bool = False) -> None:
        if (
            not isinstance(name, str)
            or not SERVER_NAME_RE.fullmatch(name)
            or name in INTERNAL_SERVER_NAMES
        ):
            self.errors.add("unparseable")
            return
        if name not in self.disabled and len(self.disabled) >= MAX_SERVER_COUNT:
            self.errors.add("unparseable")
            return
        if overwrite or name not in self.disabled:
            self.disabled[name] = disabled


@dataclass(frozen=True)
class CommandResult:
    outcome: str
    output: str = ""
    returncode: int | None = None


Runner = Callable[[Sequence[str], float, Mapping[str, str]], CommandResult]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json_object(
    path: Path,
    *,
    required: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_OUTPUT_BYTES + 1)
    except FileNotFoundError:
        return None, "unavailable" if required else None
    except OSError:
        return None, "unavailable"
    if len(payload) > MAX_OUTPUT_BYTES:
        return None, "unparseable"
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None, "unparseable"
    if not isinstance(value, dict):
        return None, "unparseable"
    return value, None


def _plugin_mcp_expectations(
    paths: RuntimePaths,
    expectations: Expectations,
    *,
    claude_namespace: bool,
) -> None:
    settings, error = _read_json_object(paths.claude_settings, required=False)
    if error:
        expectations.errors.add(error)
        return
    if settings is None:
        return

    enabled_plugins = settings.get("enabledPlugins", {})
    if not isinstance(enabled_plugins, dict):
        expectations.errors.add("unparseable")
        return
    plugin_states: dict[str, bool] = {}
    for plugin_id, enabled in enabled_plugins.items():
        if not isinstance(plugin_id, str) or not isinstance(enabled, bool):
            expectations.errors.add("unparseable")
            continue
        plugin_states[plugin_id] = enabled
    if not plugin_states:
        return

    has_enabled_plugin = any(plugin_states.values())
    index, error = _read_json_object(
        paths.plugin_index,
        required=has_enabled_plugin,
    )
    if error:
        expectations.errors.add(error)
        return
    if index is None:
        return
    installed = index.get("plugins", {})
    if not isinstance(installed, dict):
        expectations.errors.add("unparseable")
        return

    for plugin_id, enabled in plugin_states.items():
        records = installed.get(plugin_id)
        if records is None:
            if enabled:
                expectations.errors.add("unavailable")
            continue
        if not isinstance(records, list):
            if enabled:
                expectations.errors.add("unparseable")
            continue
        plugin_name = plugin_id.split("@", 1)[0]
        if not SERVER_NAME_RE.fullmatch(plugin_name):
            expectations.errors.add("unparseable")
            continue

        resolved_record = False
        for record in records:
            if not isinstance(record, dict):
                if enabled:
                    expectations.errors.add("unparseable")
                continue
            install_path = record.get("installPath")
            if not isinstance(install_path, str) or not install_path:
                if enabled:
                    expectations.errors.add("unparseable")
                continue
            install_root = Path(install_path).expanduser()
            if not install_root.is_absolute():
                if enabled:
                    expectations.errors.add("unparseable")
                continue
            if not install_root.is_dir():
                if enabled:
                    expectations.errors.add("unavailable")
                continue
            resolved_record = True
            manifest_path = install_root / ".mcp.json"
            if not manifest_path.exists():
                continue
            manifest, manifest_error = _read_json_object(
                manifest_path, required=True
            )
            if manifest_error or manifest is None:
                if enabled:
                    expectations.errors.add(manifest_error or "unparseable")
                continue
            servers = manifest.get("mcpServers")
            if not isinstance(servers, dict):
                if enabled:
                    expectations.errors.add("unparseable")
                continue
            for server_name, server in servers.items():
                if not isinstance(server, dict):
                    if enabled:
                        expectations.errors.add("unparseable")
                    continue
                separator = "plugin:" if claude_namespace else ""
                expectations.add(
                    f"{separator}{plugin_name}:{server_name}",
                    disabled=not enabled,
                )
        if enabled and not resolved_record:
            expectations.errors.add("unavailable")


def load_claude_expectations(
    paths: RuntimePaths,
    *,
    required: bool,
    claude_namespace: bool = True,
) -> Expectations:
    expectations = Expectations()
    config, error = _read_json_object(paths.claude_config, required=required)
    if error:
        expectations.errors.add(error)
    if config is not None:
        servers = config.get("mcpServers", {})
        if not isinstance(servers, dict):
            expectations.errors.add("unparseable")
        else:
            for name, server in servers.items():
                if not isinstance(server, dict):
                    expectations.errors.add("unparseable")
                    continue
                disabled = (
                    server.get("disabled") is True
                    or server.get("enabled") is False
                )
                expectations.add(name, disabled=disabled)
    _plugin_mcp_expectations(
        paths,
        expectations,
        claude_namespace=claude_namespace,
    )
    return expectations


def load_omp_expectations(paths: RuntimePaths) -> Expectations:
    expectations = Expectations()
    enabled_overrides: set[str] = set()
    disabled_overrides: set[str] = set()

    native_path = paths.omp_agent_dir / "mcp.json"
    native, native_error = _read_json_object(native_path, required=False)
    if native_error:
        expectations.errors.add(native_error)
    if native is not None:
        servers = native.get("mcpServers", {})
        if not isinstance(servers, dict):
            expectations.errors.add("unparseable")
        else:
            for name, server in servers.items():
                if not isinstance(server, dict):
                    expectations.errors.add("unparseable")
                    continue
                expectations.add(
                    name,
                    disabled=server.get("enabled") is False,
                )
        for key, target in (
            ("enabledServers", enabled_overrides),
            ("disabledServers", disabled_overrides),
        ):
            values = native.get(key, [])
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                expectations.errors.add("unparseable")
                continue
            target.update(values)

    imported = load_claude_expectations(
        paths,
        required=False,
        claude_namespace=False,
    )
    expectations.errors.update(imported.errors)
    for name, disabled in imported.disabled.items():
        expectations.add(name, disabled=disabled)

    for name in enabled_overrides:
        expectations.add(name, disabled=False, overwrite=True)
    for name in disabled_overrides:
        expectations.add(name, disabled=True, overwrite=True)
    return expectations


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1)
    except (subprocess.TimeoutExpired, ChildProcessError):
        pass


def run_bounded(
    argv: Sequence[str],
    timeout_seconds: float,
    environment: Mapping[str, str],
    *,
    popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    monotonic: Callable[[], float] = time.monotonic,
) -> CommandResult:
    """Run argv in a new process group while retaining at most 1 MiB output."""
    try:
        process = popen_factory(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(environment),
            start_new_session=True,
        )
    except (FileNotFoundError, PermissionError, OSError):
        return CommandResult("unavailable")

    if process.stdout is None:
        _kill_process_group(process)
        return CommandResult("unavailable")

    deadline = monotonic() + timeout_seconds
    output = bytearray()
    eof = False
    selector = selectors.DefaultSelector()
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector.register(descriptor, selectors.EVENT_READ)
    try:
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                _kill_process_group(process)
                return CommandResult("timeout")
            events = selector.select(min(remaining, 0.1))
            for key, _mask in events:
                try:
                    chunk = os.read(
                        key.fd,
                        min(65536, MAX_OUTPUT_BYTES + 1 - len(output)),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    try:
                        selector.unregister(key.fd)
                    except KeyError:
                        pass
                    continue
                output.extend(chunk)
                if len(output) > MAX_OUTPUT_BYTES:
                    _kill_process_group(process)
                    return CommandResult("overflow")
            if process.poll() is not None and eof:
                break
        returncode = process.wait(timeout=max(0.01, deadline - monotonic()))
    except (OSError, subprocess.SubprocessError):
        _kill_process_group(process)
        return CommandResult("unavailable")
    finally:
        selector.close()
        process.stdout.close()

    try:
        decoded = output.decode("utf-8")
    except UnicodeDecodeError:
        return CommandResult("unparseable", returncode=returncode)
    return CommandResult("completed", decoded, returncode)


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
        "degraded"
        if any(item["status"] == "degraded" for item in ordered)
        else "ok"
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
        rows.extend(
            _row(name, "degraded", "timeout") for name in failure_targets
        )
    elif result.outcome in {"overflow", "unparseable"}:
        rows.extend(
            _row(name, "degraded", "unparseable") for name in failure_targets
        )
    elif result.outcome != "completed" or result.returncode != 0:
        rows.extend(
            _row(name, "degraded", "unavailable") for name in failure_targets
        )
    elif not result.output.strip():
        rows.extend(
            _row(name, "degraded", "unparseable") for name in failure_targets
        )
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
        if (
            SERVER_NAME_RE.fullmatch(name)
            and name not in INTERNAL_SERVER_NAMES
        ):
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
    return parsed.astimezone(timezone.utc)


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
    current = now.astimezone(timezone.utc)
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


def _prepare_state_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _try_probe_lock(paths: RuntimePaths, harness: str) -> tuple[int | None, bool]:
    descriptor: int | None = None
    try:
        _prepare_state_dir(paths.state_dir)
        descriptor = os.open(
            paths.state_dir / f"mcp-{harness}.lock",
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return descriptor, False
        return descriptor, True
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        return None, False


def _release_probe_lock(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        pass
    os.close(descriptor)


def _atomic_write_report(path: Path, report: Mapping[str, Any]) -> bool:
    temporary_name: str | None = None
    try:
        _prepare_state_dir(path.parent)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


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
    expectations = (
        load_claude_expectations(paths, required=True)
        if harness == "claude"
        else load_omp_expectations(paths)
    )
    if not probe:
        cached = _fresh_cached_report(paths, harness, expectations, clock)
        if cached is not None:
            return cached
        return _not_probed_report(harness, expectations, clock)

    lock_descriptor, acquired = _try_probe_lock(paths, harness)
    if not acquired:
        try:
            cached = _fresh_cached_report(paths, harness, expectations, clock)
            if cached is not None:
                return cached
            if lock_descriptor is not None:
                return _not_probed_report(
                    harness,
                    expectations,
                    clock,
                    reason="probe_in_progress",
                )
            return _append_degraded_row(
                _not_probed_report(harness, expectations, clock),
                "__state__",
                "unavailable",
                clock,
            )
        finally:
            _release_probe_lock(lock_descriptor)

    try:
        if harness == "claude":
            report = probe_claude(
                paths,
                expectations,
                timeout_seconds,
                environment,
                runner,
                clock,
            )
        else:
            report = probe_omp(
                expectations,
                inventory_observed=inventory_observed,
                observed_servers=observed_servers,
                clock=clock,
            )
        if not _atomic_write_report(_cache_path(paths, harness), report):
            return _append_degraded_row(
                report,
                "__state__",
                "unavailable",
                clock,
            )
        return report
    finally:
        _release_probe_lock(lock_descriptor)


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
    parser.add_argument("--probe", action="store_true", help="force a fresh observation")
    parser.add_argument("--harness", required=True, choices=("claude", "omp"))
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_capped_timeout,
        default=MAX_TIMEOUT_SECONDS,
    )
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--inventory-observed", action="store_true", help=argparse.SUPPRESS)
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
