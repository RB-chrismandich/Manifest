"""Expected MCP server inventory: runtime paths and config-derived expectations."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_health_runtime import _read_json_object

MAX_SERVER_COUNT = 1000
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
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
    ) -> RuntimePaths:
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


def _plugin_states(
    paths: RuntimePaths,
    expectations: Expectations,
) -> dict[str, bool] | None:
    """Read enabledPlugins from Claude settings; None means stop processing."""
    settings, error = _read_json_object(paths.claude_settings, required=False)
    if error:
        expectations.errors.add(error)
        return None
    if settings is None:
        return None

    enabled_plugins = settings.get("enabledPlugins", {})
    if not isinstance(enabled_plugins, dict):
        expectations.errors.add("unparseable")
        return None
    plugin_states: dict[str, bool] = {}
    for plugin_id, enabled in enabled_plugins.items():
        if not isinstance(plugin_id, str) or not isinstance(enabled, bool):
            expectations.errors.add("unparseable")
            continue
        plugin_states[plugin_id] = enabled
    return plugin_states


def _record_server_expectations(
    record: object,
    plugin_name: str,
    enabled: bool,
    expectations: Expectations,
    claude_namespace: bool,
) -> bool:
    """Add expectations from one install record; True if the record resolved."""
    if not isinstance(record, dict):
        if enabled:
            expectations.errors.add("unparseable")
        return False
    install_path = record.get("installPath")
    if not isinstance(install_path, str) or not install_path:
        if enabled:
            expectations.errors.add("unparseable")
        return False
    install_root = Path(install_path).expanduser()
    if not install_root.is_absolute():
        if enabled:
            expectations.errors.add("unparseable")
        return False
    if not install_root.is_dir():
        if enabled:
            expectations.errors.add("unavailable")
        return False
    manifest_path = install_root / ".mcp.json"
    if not manifest_path.exists():
        return True
    manifest, manifest_error = _read_json_object(manifest_path, required=True)
    if manifest_error or manifest is None:
        if enabled:
            expectations.errors.add(manifest_error or "unparseable")
        return True
    servers = manifest.get("mcpServers")
    if not isinstance(servers, dict):
        if enabled:
            expectations.errors.add("unparseable")
        return True
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
    return True


def _plugin_server_expectations(
    plugin_id: str,
    enabled: bool,
    records: object,
    expectations: Expectations,
    claude_namespace: bool,
) -> None:
    if records is None:
        if enabled:
            expectations.errors.add("unavailable")
        return
    if not isinstance(records, list):
        if enabled:
            expectations.errors.add("unparseable")
        return
    plugin_name = plugin_id.split("@", 1)[0]
    if not SERVER_NAME_RE.fullmatch(plugin_name):
        expectations.errors.add("unparseable")
        return

    resolved_record = False
    for record in records:
        resolved_record = (
            _record_server_expectations(
                record,
                plugin_name,
                enabled,
                expectations,
                claude_namespace,
            )
            or resolved_record
        )
    if enabled and not resolved_record:
        expectations.errors.add("unavailable")


def _plugin_mcp_expectations(
    paths: RuntimePaths,
    expectations: Expectations,
    *,
    claude_namespace: bool,
) -> None:
    plugin_states = _plugin_states(paths, expectations)
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
        _plugin_server_expectations(
            plugin_id,
            enabled,
            installed.get(plugin_id),
            expectations,
            claude_namespace,
        )


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
                    server.get("disabled") is True or server.get("enabled") is False
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
