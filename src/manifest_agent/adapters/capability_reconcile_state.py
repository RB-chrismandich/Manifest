"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from manifest_agent.adapters.capability_inventory import (
    normalize_native_mcp_inventory,
)
from manifest_agent.capabilities import CapabilityPlan
from manifest_agent.capability_cursor import cursor_mcp_path
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackup,
    OwnedFileBackup,
    plugin_tree_sha256,
    read_owned_file_backup,
    verify_owned_file_backup,
    verify_plugin_backup,
)
from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessReceipt,
)
from manifest_agent.process import redact_text


class ReconcileStateMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def _desired_reconcile_inventory(
        self, desired: DesiredState
    ) -> tuple[AdapterPluginState, ...]:
        suffix = "@manifest" if self.name in {"claude", "codex"} else ""
        return tuple(
            AdapterPluginState(
                f"{contract.name}{suffix}",
                contract.version,
                True,
                installed_sha256=(
                    self._expected_reconcile_tree_digest(desired, contract.name)
                ),
                source_identity=self._expected_reconcile_source_identity(
                    desired, contract.name
                ),
            )
            for contract in desired.all_contracts
        )

    def _expected_reconcile_source_identity(
        self, desired: DesiredState, bundle: str
    ) -> str:
        del bundle
        return desired.marketplace_source.source

    def _expected_reconcile_tree_digest(
        self, desired: DesiredState, bundle: str
    ) -> str | None:
        path = desired.bundle_path(bundle)
        return plugin_tree_sha256(path) if path.is_dir() else None

    def _capture_reconcile_inventory(
        self, receipt: HarnessReceipt, prior: DesiredState
    ) -> tuple[AdapterPluginState, ...]:
        observer = getattr(self, "_native_reconcile_inventory", None)
        if observer is None:
            raise ValueError(
                f"{self.name} cannot capture exact native reconciliation state"
            )
        inventory = tuple(observer(prior, capture_backups=True))
        expected_ids = {
            item.identifier for item in self._desired_reconcile_inventory(prior)
        }
        if {item.identifier for item in inventory} != expected_ids:
            raise ValueError(
                f"{self.name} exact native reconciliation capture is incomplete"
            )
        return inventory

    def _reconcile_backup_error(self, handle: AdapterMutationHandle) -> str | None:
        try:
            for item in handle.prior_inventory:
                if item.installed_path is None:
                    continue
                if item.rollback_data is None:
                    return f"exact rollback backup is missing for {item.identifier}"
                verify_plugin_backup(CodexPluginBackup.from_dict(item.rollback_data))
            for row in handle.prior_owned_files:
                restore = row.get("restore")
                if restore is None:
                    continue
                if not isinstance(restore, dict) or not isinstance(
                    restore.get("archive"), dict
                ):
                    return f"exact owned-file rollback backup is missing for {row.get('path')}"
                verify_owned_file_backup(
                    OwnedFileBackup.from_dict(restore["archive"]),
                    self._env,
                )
        except Exception as error:
            return f"exact rollback backup is invalid: {redact_text(str(error))}"
        return None

    def _reconcile_capability_state(self, desired: DesiredState) -> dict[str, str]:
        plan = _resolve_capabilities(
            desired.all_contracts, selected_optional=desired.selected_optional
        )
        state: dict[str, str] = {}
        native_mcp = normalize_native_mcp_inventory(self._native_mcp_inventory)
        for name in plan.selected_mcp:
            state[f"mcp:{name}"] = "present" if name in native_mcp else "absent"
        for name in plan.selected_executables:
            resolved = self._which(name)
            state[f"executable:{name}"] = (
                str(Path(resolved).resolve()) if resolved else "absent"
            )
        return state

    def _expected_reconcile_capability_state(
        self, desired: DesiredState
    ) -> dict[str, str]:
        plan = _resolve_capabilities(
            desired.all_contracts, selected_optional=desired.selected_optional
        )
        state = {f"mcp:{name}": "present" for name in plan.selected_mcp}
        for name in plan.selected_executables:
            state[f"executable:{name}"] = self._expected_reconcile_executable_path(
                name, desired, plan
            )
        return state

    def _expected_reconcile_executable_path(
        self, name: str, desired: DesiredState, plan: CapabilityPlan
    ) -> str:
        """Return the deterministic post-install executable identity."""
        del desired
        recipe = plan.executable_definitions.get(name)
        if recipe is not None:
            environment = dict(os.environ)
            if self._env is not None:
                environment.update(self._env)
            configured = environment.get("UV_TOOL_BIN_DIR") or environment.get(
                "XDG_BIN_HOME"
            )
            if configured:
                root = Path(configured)
            else:
                home = Path(environment.get("HOME", str(Path.home())))
                root = home / ".local" / "bin"
            return str((root / recipe.executable).resolve())
        resolved = self._which(name)
        return str(Path(resolved).resolve()) if resolved else "absent"

    def _expected_reconcile_owned_files(
        self, receipt: HarnessReceipt, desired: DesiredState
    ) -> tuple[dict[str, object], ...]:
        """Model exact post-install bytes for adapter-owned filesystem targets."""
        return self._expected_reconcile_owned_files_from_prior(
            self._capture_receipt_owned_files(receipt), desired
        )

    def _expected_reconcile_owned_files_from_prior(
        self,
        prior: tuple[dict[str, object], ...],
        desired: DesiredState,
    ) -> tuple[dict[str, object], ...]:
        if self.name != "cursor":
            if prior:
                raise ValueError(
                    f"{self.name} cannot model exact target owned filesystem state"
                )
            return ()

        path = cursor_mcp_path(self._env)
        unexpected = tuple(item for item in prior if item.get("path") != str(path))
        if unexpected:
            raise ValueError("Cursor receipt contains an unsupported owned file target")
        plan = _resolve_capabilities(
            desired.all_contracts, selected_optional=desired.selected_optional
        )
        prior_row = next(
            (item for item in prior if item.get("path") == str(path)), None
        )
        document = self._cursor_prior_document(prior_row)
        servers = document.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise ValueError("Cursor mcpServers must be a JSON object")
        changed = self._add_cursor_mcp_entries(servers, plan)
        if not changed:
            return prior
        payload = (json.dumps(document, indent=2) + "\n").encode()
        mode = (
            0o600 if changed or not path.exists() else stat.S_IMODE(path.stat().st_mode)
        )
        return (
            {
                "path": str(path),
                "type": "file",
                "mode": mode,
                "digest": hashlib.sha256(payload).hexdigest(),
            },
        )

    def _cursor_prior_document(
        self, prior_row: dict[str, object] | None
    ) -> dict[str, object]:
        if prior_row is None or prior_row.get("type") == "missing":
            return {}
        restore = prior_row.get("restore")
        if (
            prior_row.get("type") != "file"
            or not isinstance(restore, dict)
            or not isinstance(restore.get("archive"), dict)
        ):
            raise ValueError("Cursor owned file backup is not rollback-safe")
        try:
            decoded = read_owned_file_backup(
                OwnedFileBackup.from_dict(restore["archive"]), self._env
            )
            document = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Cursor owned file backup is invalid") from error
        if not isinstance(document, dict):
            raise ValueError("Cursor MCP configuration must be a JSON object")
        return document

    def _add_cursor_mcp_entries(
        self, servers: dict[str, object], plan: CapabilityPlan
    ) -> bool:
        native_names = set(normalize_native_mcp_inventory(self._native_mcp_inventory))
        changed = False
        for name in plan.selected_mcp:
            definition = plan.mcp_definitions[name]
            if name in native_names or definition.transport == "native-existing":
                continue
            key = f"manifest-{name}"
            expected = {"url": definition.url}
            current = servers.get(key)
            if current is not None and current != expected:
                raise ValueError(f"conflicting Cursor MCP entry {key}")
            if current is None:
                servers[key] = expected
                changed = True
        return changed


def _resolve_capabilities(*args, **kwargs):
    from manifest_agent.adapters import capability_lifecycle

    return capability_lifecycle.resolve_capabilities(*args, **kwargs)
