"""Codex plugin installation, repair, and ADHD hook probing."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from manifest_agent.adapters.base import combine_results
from manifest_agent.adapters.codex_catalog import (
    catalog,
    catalog_owned_entries,
    row_is_ready,
    validate_desired,
)
from manifest_agent.adapters.codex_common import ADHD_PLUGIN, MARKETPLACE, blocked
from manifest_agent.adapters.codex_marketplace import (
    marketplace_add_argv,
    validate_marketplace_add,
    validate_plugin_add,
)
from manifest_agent.adapters.codex_native import installed_plugin_path, plugin_rows
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackup,
    CodexPluginBackupError,
    capture_plugin_backup,
    restore_plugin_backup,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    CatalogPlugin,
    CommandResult,
    DesiredState,
    HarnessResult,
    ResultState,
)

RepairCheckpoint = Callable[[CodexPluginBackup, str], None]


class AdhdProbeError(ValueError):
    """The installed ADHD hook cannot be authenticated or executed safely."""


class CodexInstallMixin:
    """Install and repair the exact catalog declared by a desired release."""

    if TYPE_CHECKING:
        name: str
        _env: Mapping[str, str] | None
        _which: Callable[[str], str | None]
        _last_marketplace_identity: AdapterMarketplaceState | None
        _execute: Callable[
            [Sequence[str]], tuple[CommandResult | None, HarnessResult | None]
        ]
        _inspect_marketplace: Callable[[DesiredState], HarnessResult]
        _list_installed_manifest_rows: Callable[
            [], tuple[dict[str, Mapping[str, Any]] | None, HarnessResult | None]
        ]
        _observed_marketplace_identity: Callable[..., AdapterMarketplaceState | None]
        _run_json_mutations: Callable[[Sequence[Sequence[str]]], list[HarnessResult]]
        inspect: Callable[[DesiredState], HarnessResult]
        install_capabilities: Callable[[DesiredState], HarnessResult]

    def probe_adhd_hook(self, desired: DesiredState) -> HarnessResult:
        """Execute the installed addon hook and require canonical activation output."""
        addon = next(
            (plugin for plugin in catalog(desired) if plugin.name == ADHD_PLUGIN), None
        )
        if addon is None:
            return blocked("canonical ADHD addon is missing from the catalog")
        plugin_id, row, failure = _installed_addon_row(self, addon)
        if failure is not None or row is None:
            return failure or blocked(
                "installed ADHD addon identity is not probe-ready"
            )
        try:
            launcher, expected_stdout = _authenticated_probe(desired, addon, row)
        except AdhdProbeError as error:
            return blocked(str(error))
        completed = _execute_probe(self._which, self._env, launcher)
        if completed is None:
            return blocked("installed ADHD SessionStart probe could not execute")
        if (
            completed.returncode != 0
            or completed.stdout != expected_stdout
            or completed.stderr != ""
        ):
            return blocked("installed ADHD SessionStart probe did not activate")
        return HarnessResult(
            self.name,
            ResultState.READY,
            (plugin_id,),
            {f"addon:{addon.name}:session-start": "verified"},
        )

    def install_with_checkpoints(
        self,
        desired: DesiredState,
        repair_checkpoint: RepairCheckpoint | None = None,
        *,
        marketplace_preverified: bool = False,
    ) -> HarnessResult:
        """Install while durably checkpointing destructive plugin repairs."""
        invalid = validate_desired(desired)
        if invalid is not None:
            return invalid
        marketplace = _prepare_marketplace(self, desired, marketplace_preverified)
        if marketplace is not None:
            return marketplace
        rows, error = self._list_installed_manifest_rows()
        if error is not None or rows is None:
            return error or blocked("Codex plugin inventory is unavailable")
        failures: list[HarnessResult] = []
        for plugin in catalog(desired):
            failures.extend(
                _repair_plugin(
                    self,
                    desired,
                    plugin,
                    rows.get(_plugin_id(plugin)),
                    repair_checkpoint,
                )
            )
        capabilities = self.install_capabilities(desired)
        inspected = self.inspect(desired)
        marketplace_identity = (
            self._last_marketplace_identity or self._observed_marketplace_identity()
        )
        ownership = HarnessResult(
            self.name,
            ResultState.READY,
            (),
            {},
            owned_entries=catalog_owned_entries(
                desired, self._env, marketplace_identity
            ),
        )
        return combine_results(*failures, capabilities, inspected, ownership)

    def _recover_ambiguous_removal(
        self,
        backup: CodexPluginBackup,
        desired: DesiredState,
        plugin: CatalogPlugin,
        repair_checkpoint: RepairCheckpoint | None,
    ) -> HarnessResult | None:
        command, error = self._execute((self.name, "plugin", "list", "--json"))
        rows: list[Mapping[str, Any]] = []
        if error is None and command is not None and command.returncode == 0:
            rows, parse_error = plugin_rows(command.stdout, self._env)
            if parse_error is not None:
                rows = []
        row = next(
            (item for item in rows if item.get("pluginId") == _plugin_id(plugin)), None
        )
        if isinstance(row, Mapping) and row_is_ready(row, plugin, desired):
            if repair_checkpoint is not None:
                repair_checkpoint(backup, "added")
            return None

        installed = installed_plugin_path(row) if isinstance(row, Mapping) else None
        if (
            isinstance(row, Mapping)
            and row.get("version") == backup.version
            and row.get("enabled") is backup.enabled
            and isinstance(installed, str)
            and Path(installed).resolve(strict=False)
            == Path(backup.installed_path).resolve(strict=False)
        ):
            if repair_checkpoint is not None:
                repair_checkpoint(backup, "restored")
            return blocked(
                "plugin removal failed; verified prior plugin remains installed"
            )
        try:
            restore_plugin_backup(backup)
            if repair_checkpoint is not None:
                repair_checkpoint(backup, "restored")
        except CodexPluginBackupError:
            return blocked(
                "plugin removal outcome is ambiguous and the verified backup could not "
                "be restored without overwriting later state"
            )
        return blocked("plugin removal failed; verified prior plugin was restored")


def _installed_addon_row(
    adapter: CodexInstallMixin, addon: CatalogPlugin
) -> tuple[str, Mapping[str, Any] | None, HarnessResult | None]:
    command, error = adapter._execute((adapter.name, "plugin", "list", "--json"))
    if error is not None:
        return "", None, error
    assert command is not None
    rows, parse_error = plugin_rows(command.stdout, adapter._env)
    if parse_error is not None:
        return "", None, blocked(parse_error)
    plugin_id = _plugin_id(addon)
    row = next((item for item in rows if item.get("pluginId") == plugin_id), None)
    installed = installed_plugin_path(row) if isinstance(row, Mapping) else None
    if (
        not isinstance(row, Mapping)
        or row.get("version") != addon.version
        or row.get("enabled") is False
        or not isinstance(installed, str)
    ):
        return (
            plugin_id,
            None,
            blocked("installed ADHD addon identity is not probe-ready"),
        )
    return plugin_id, row, None


def _authenticated_probe(
    desired: DesiredState, addon: CatalogPlugin, row: Mapping[str, Any]
) -> tuple[Path, str]:
    installed = installed_plugin_path(row)
    if installed is None:
        raise AdhdProbeError(
            "installed ADHD SessionStart launcher is missing or unsafe"
        )
    try:
        installed_root = Path(installed).resolve(strict=True)
        hook_manifest = installed_root / "hooks" / "hooks.json"
        launcher = _registered_session_start_launcher(installed_root, hook_manifest)
        guidance = installed_root / "guidance" / "always-on.md"
        if (
            any(
                path.is_symlink()
                or not path.is_file()
                or path.resolve(strict=True) != path
                for path in (hook_manifest, launcher, guidance)
            )
            or Path(installed).is_symlink()
        ):
            raise ValueError("unsafe installed asset")
    except (OSError, ValueError) as error:
        raise AdhdProbeError(
            "installed ADHD SessionStart launcher is missing or unsafe"
        ) from error
    return launcher, _authenticated_probe_stdout(
        desired,
        addon,
        installed_root,
        {
            "hooks/hooks.json": hook_manifest,
            "hooks/always_on.py": launcher,
            "guidance/always-on.md": guidance,
        },
    )


def _authenticated_probe_stdout(
    desired: DesiredState,
    addon: CatalogPlugin,
    installed_root: Path,
    installed_assets: Mapping[str, Path],
) -> str:
    del installed_root
    try:
        desired_root = desired.bundle_path(addon.name).resolve(strict=True)
        desired_assets = {name: desired_root / name for name in installed_assets}
        if any(
            source.is_symlink()
            or not source.is_file()
            or source.read_bytes() != installed_assets[name].read_bytes()
            for name, source in desired_assets.items()
        ):
            raise AdhdProbeError("installed ADHD hook artifacts failed authentication")
        canonical = (
            desired_assets["guidance/always-on.md"].read_text(encoding="utf-8").rstrip()
        )
    except AdhdProbeError:
        raise
    except (OSError, UnicodeError) as error:
        raise AdhdProbeError(
            "installed ADHD canonical guidance is unreadable"
        ) from error
    return f"Manifest ADHD guidance v{addon.version}\n\n{canonical}\n"


def _execute_probe(
    which: Callable[[str], str | None],
    configured_env: Mapping[str, str] | None,
    launcher: Path,
) -> subprocess.CompletedProcess[str] | None:
    payload = json.dumps({"hook_event_name": "SessionStart"})
    try:
        with tempfile.TemporaryDirectory(prefix="manifest-adhd-probe-") as state:
            values = dict(os.environ)
            if configured_env:
                values.update(configured_env)
            environment = {
                key: values[key]
                for key in ("LANG", "LC_ALL", "PATH", "PYTHONUTF8")
                if key in values
            }
            environment["MANIFEST_STATE_ROOT"] = state
            return subprocess.run(
                (which("python3") or "python3", str(launcher)),
                input=payload,
                capture_output=True,
                text=True,
                timeout=10,
                env=environment,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return None


def _prepare_marketplace(
    adapter: CodexInstallMixin,
    desired: DesiredState,
    preverified: bool,
) -> HarnessResult | None:
    add_failure = None
    if not preverified:
        command, execution_error = adapter._execute(marketplace_add_argv(desired))
        add_failure = execution_error
        if command is not None:
            add_failure = validate_marketplace_add(command)
    marketplace = adapter._inspect_marketplace(desired)
    if marketplace.state is ResultState.READY and add_failure is None:
        return None
    return combine_results(
        *(result for result in (add_failure, marketplace) if result is not None)
    )


def _repair_plugin(
    adapter: CodexInstallMixin,
    desired: DesiredState,
    plugin: CatalogPlugin,
    row: Mapping[str, Any] | None,
    checkpoint: RepairCheckpoint | None,
) -> list[HarnessResult]:
    if row is not None and row_is_ready(row, plugin, desired):
        return []
    backup, failures = _remove_stale_plugin(adapter, desired, plugin, row, checkpoint)
    if failures is None:
        return []
    if failures:
        return failures
    add_failure = _add_plugin(adapter, plugin)
    if add_failure is None:
        if backup is not None and checkpoint is not None:
            checkpoint(backup, "added")
        return []
    if backup is None:
        return [add_failure]
    restore_failure = _restore_backup(backup, checkpoint)
    return [add_failure, *([restore_failure] if restore_failure else [])]


def _remove_stale_plugin(
    adapter: CodexInstallMixin,
    desired: DesiredState,
    plugin: CatalogPlugin,
    row: Mapping[str, Any] | None,
    checkpoint: RepairCheckpoint | None,
) -> tuple[CodexPluginBackup | None, list[HarnessResult] | None]:
    if row is None:
        return None, []
    try:
        backup = capture_plugin_backup(row, adapter._env)
        if checkpoint is not None:
            checkpoint(backup, "captured")
    except CodexPluginBackupError as error:
        return None, [blocked(str(error))]
    failures = adapter._run_json_mutations(
        [(adapter.name, "plugin", "remove", _plugin_id(plugin), "--json")]
    )
    if failures:
        recovered = adapter._recover_ambiguous_removal(
            backup, desired, plugin, checkpoint
        )
        return backup, [*failures, recovered] if recovered is not None else None
    if checkpoint is not None:
        checkpoint(backup, "removed")
    return backup, []


def _add_plugin(
    adapter: CodexInstallMixin, plugin: CatalogPlugin
) -> HarnessResult | None:
    command, error = adapter._execute(
        (adapter.name, "plugin", "add", _plugin_id(plugin), "--json")
    )
    if error is not None:
        return error
    assert command is not None
    return validate_plugin_add(command, plugin.name, plugin.version)


def _restore_backup(
    backup: CodexPluginBackup, checkpoint: RepairCheckpoint | None
) -> HarnessResult | None:
    try:
        restore_plugin_backup(backup)
        if checkpoint is not None:
            checkpoint(backup, "restored")
    except CodexPluginBackupError as error:
        return blocked(
            "plugin restoration failed; rerun manifest bootstrap-sync after preserving "
            f"{backup.archive_path}: {error}"
        )
    return None


def _plugin_id(plugin: CatalogPlugin) -> str:
    return f"{plugin.name}@{MARKETPLACE}"


def _registered_session_start_launcher(root: Path, path: Path) -> Path:
    """Return the exact launcher registered by the installed hooks manifest."""
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
        raise ValueError("unsafe hook manifest")
    document = json.loads(path.read_text(encoding="utf-8"))
    hooks = document.get("hooks") if isinstance(document, Mapping) else None
    session = hooks.get("SessionStart") if isinstance(hooks, Mapping) else None
    if not isinstance(session, list) or len(session) != 1:
        raise ValueError("invalid SessionStart registration")
    group = session[0]
    commands = group.get("hooks") if isinstance(group, Mapping) else None
    if not isinstance(commands, list) or len(commands) != 1:
        raise ValueError("invalid SessionStart command group")
    command = commands[0]
    if not isinstance(command, Mapping) or set(command) != {"command", "type"}:
        raise ValueError("invalid SessionStart command")
    if (
        command.get("type") != "command"
        or command.get("command") != "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/always_on.py"
    ):
        raise ValueError("unexpected SessionStart command")
    launcher = root / "hooks" / "always_on.py"
    if launcher.parent != root / "hooks":
        raise ValueError("SessionStart launcher escaped plugin root")
    return launcher
