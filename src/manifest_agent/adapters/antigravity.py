"""Antigravity CLI native plugin adapter."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from manifest_agent.adapters.antigravity_evidence import (
    _component_evidence,
    _expected_skill_paths,
)
from manifest_agent.adapters.base import (
    CapabilityAdapterMixin,
    Detection,
    NativeMcpInventory,
    combine_results,
    native_command_result,
    normalize_native_mcp_inventory,
    verify_declared_components,
)
from manifest_agent.adapters.capability_receipt import (
    expected_uninstall_plugin_ids,
)
from manifest_agent.contracts import DOMAIN_BUNDLES, PORTABLE_BUNDLES
from manifest_agent.models import (
    AdapterPluginState,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

_ADAPTER_VERSION = "1"
_MARKETPLACE = "manifest"


class AntigravityAdapter(CapabilityAdapterMixin):
    """Validate and import the exact verified Manifest release through ``agy``."""

    name = "antigravity"
    executable = "agy"
    adapter_version = _ADAPTER_VERSION

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        which: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
        native_mcp_inventory: NativeMcpInventory = (),
    ) -> None:
        self.runner = runner or CommandRunner()
        self._which = which
        self._env = env
        self._native_mcp_inventory = normalize_native_mcp_inventory(
            native_mcp_inventory
        )

    def detect(self) -> Detection:
        """Report Antigravity CLI availability and its native version."""
        executable = self._which(self.executable)
        if executable is None:
            return Detection(False, None, None, "agy CLI not present")
        command, error = self._execute((executable, "--version"))
        if error is not None:
            return Detection(True, executable, None, error.errors[0])
        assert command is not None
        if command.returncode != 0:
            result = native_command_result(self.name, command, CapabilityTier.REQUIRED)
            return Detection(True, executable, None, result.errors[0])
        lines = command.stdout.strip().splitlines()
        return Detection(
            True,
            executable,
            redact_text(lines[0]) if lines else None,
        )

    def inspect(self, desired: DesiredState) -> HarnessResult:
        """Verify all canonical imports and their native skill exposure."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        command, error = self._execute((self.executable, "plugin", "list"))
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        rows, parse_error = _import_rows(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        plugins = _verify_imports(desired, rows)
        evidence = _component_evidence(desired, rows, self._which)
        components = verify_declared_components(self.name, desired, evidence)
        return combine_results(plugins, components)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Validate all canonical bundles before linking or installing any plugin."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid

        validation_failures = self._run_mutations(
            [
                (
                    self.executable,
                    "plugin",
                    "validate",
                    str(desired.bundle_path(name)),
                )
                for name in (contract.name for contract in desired.all_contracts)
            ]
        )
        if validation_failures:
            return combine_results(*validation_failures)

        link_failures = self._run_mutations(
            [
                (
                    self.executable,
                    "plugin",
                    "link",
                    _MARKETPLACE,
                    str(desired.release_root),
                )
            ]
        )
        if link_failures:
            return combine_results(*link_failures)

        install_failures = self._run_mutations(
            [
                (
                    self.executable,
                    "plugin",
                    "install",
                    f"{name}@{_MARKETPLACE}",
                )
                for name in (contract.name for contract in desired.all_contracts)
            ]
        )
        capabilities = self.install_capabilities(desired)
        inspected = self.inspect(desired)
        return combine_results(*install_failures, capabilities, inspected)

    def _native_reconcile_inventory(
        self,
        desired: DesiredState,
        *,
        capture_backups: bool,
        identifiers: set[str] | None = None,
    ) -> tuple[AdapterPluginState, ...]:
        del capture_backups
        command, error = self._execute((self.executable, "plugin", "list"))
        if error is not None or command is None:
            raise ValueError("Antigravity plugin inventory is unavailable")
        rows, parse_error = _import_rows(command.stdout)
        if parse_error is not None:
            raise ValueError(parse_error)
        selected = identifiers or {contract.name for contract in desired.all_contracts}
        inventory = []
        for row in rows:
            name = row.get("name")
            if name not in selected:
                continue
            version = row.get("version")
            source = row.get("source")
            components = row.get("components")
            if (
                not isinstance(version, str)
                or not isinstance(source, str)
                or not isinstance(components, list)
                or not all(isinstance(item, str) for item in components)
            ):
                raise ValueError(
                    "Antigravity plugin inventory lacks exact native metadata"
                )
            inventory.append(
                AdapterPluginState(
                    name,
                    version,
                    True,
                    source_identity=json.dumps(
                        {"components": components, "source": source},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
        return tuple(sorted(inventory, key=lambda item: item.identifier))

    def _expected_reconcile_source_identity(
        self, desired: DesiredState, bundle: str
    ) -> str:
        contract = next(item for item in desired.all_contracts if item.name == bundle)
        components = ["skills"]
        components.extend(
            f"{kind}:{component.stable_id}"
            for kind, values in (
                ("guidance", contract.components.guidance),
                ("hook", contract.components.hooks),
                ("runtime", contract.components.runtime),
            )
            for component in values
        )
        return json.dumps(
            {"components": components, "source": _MARKETPLACE},
            sort_keys=True,
            separators=(",", ":"),
        )

    def _expected_reconcile_tree_digest(
        self, desired: DesiredState, bundle: str
    ) -> str | None:
        del desired, bundle
        return None

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Uninstall only canonical plugin identifiers recorded in the receipt."""
        plugin_ids, id_errors = _receipt_plugin_ids(receipt)
        invalid = self.validate_uninstall_receipt(
            receipt,
            plugin_ids,
            expected_uninstall_plugin_ids(plugin_ids),
            identity_errors=id_errors,
        )
        if invalid is not None:
            return invalid
        capabilities = self.remove_capabilities(receipt)
        failures: list[HarnessResult] = []
        failures.extend(
            self._run_mutations(
                [
                    (self.executable, "plugin", "uninstall", plugin_id)
                    for plugin_id in plugin_ids
                ]
            )
        )
        success = HarnessResult(self.name, ResultState.READY, (), {})
        return combine_results(capabilities, *failures, success)

    def _run_mutations(self, commands: Sequence[Sequence[str]]) -> list[HarnessResult]:
        failures: list[HarnessResult] = []
        for argv in commands:
            command, error = self._execute(argv)
            if error is not None:
                failures.append(error)
            elif command is not None and command.returncode != 0:
                failures.append(
                    native_command_result(self.name, command, CapabilityTier.REQUIRED)
                )
        return failures

    def _execute(
        self, argv: Sequence[str]
    ) -> tuple[CommandResult | None, HarnessResult | None]:
        try:
            return self.runner.run(argv, env=self._env), None
        # constitution: exempt C-ERR -- adapter boundary returns redacted errors.
        except Exception as error:
            diagnostic = redact_text(
                f"native command execution failed ({type(error).__name__}): {error}"
            )
            return None, _blocked(diagnostic)


def _validate_desired(desired: DesiredState) -> HarnessResult | None:
    if tuple(contract.name for contract in desired.contracts) != DOMAIN_BUNDLES:
        return _blocked("desired state must contain the exact canonical domains")
    if any(not contract.version for contract in desired.all_contracts):
        return _blocked("desired plugin versions must be non-empty")
    unsupported = [
        contract.compatibility["antigravity"].reason
        for contract in desired.all_contracts
        if contract.compatibility["antigravity"].mode == "unsupported"
    ]
    if unsupported:
        return _blocked(
            "Antigravity delivery is unsupported: " + "; ".join(unsupported)
        )
    errors = _generic_view_errors(desired, "antigravity")
    errors.extend(_extension_context_errors(desired))
    if errors:
        return _blocked("invalid generic plugin view: " + "; ".join(errors))
    return None


def _extension_context_errors(desired: DesiredState) -> list[str]:
    errors: list[str] = []
    for contract in desired.all_contracts:
        expected = tuple(
            component.path
            for component in contract.components.guidance
            if component.compatibility is None
            or (
                component.compatibility.get("antigravity") is not None
                and component.compatibility["antigravity"].mode
                not in {"not_applicable", "unsupported"}
            )
        )
        if not expected:
            continue
        extension = desired.bundle_path(contract.name) / "antigravity-extension.json"
        try:
            document = json.loads(extension.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            errors.append(
                f"{contract.name} has no readable Antigravity extension context"
            )
            continue
        context = (
            document.get("contextFileName") if isinstance(document, Mapping) else None
        )
        actual = (context,) if isinstance(context, str) else context
        if not isinstance(actual, (list, tuple)) or tuple(actual) != expected:
            errors.append(
                f"{contract.name} Antigravity extension context does not match "
                "its selected contract"
            )
    return errors


def _generic_view_errors(desired: DesiredState, harness: str) -> list[str]:
    errors: list[str] = []
    for contract in desired.all_contracts:
        path = desired.bundle_path(contract.name) / "plugin.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"{contract.name} has no readable plugin.json")
            continue
        if not isinstance(document, Mapping):
            errors.append(f"{contract.name} plugin.json is not an object")
            continue
        harnesses = document.get("harnesses")
        surface = harnesses.get(harness) if isinstance(harnesses, Mapping) else None
        expected_skills = _expected_skill_paths(desired, contract.name)
        if (
            not expected_skills
            or document.get("name") != contract.name
            or document.get("version") != contract.version
            or document.get("skills") != list(expected_skills)
            or not isinstance(surface, Mapping)
            or surface.get("mode") != contract.compatibility[harness].mode
            or surface.get("skills") != list(expected_skills)
        ):
            errors.append(f"{contract.name} does not match its selected contract")
            continue
    return errors


def _import_rows(
    stdout: str,
) -> tuple[list[Mapping[str, Any]], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return [], "agy plugin list did not return valid JSON"
    if not isinstance(document, Mapping):
        return [], "agy plugin list JSON has an invalid schema"
    rows = document.get("imports")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        return [], "agy plugin list JSON has an invalid imports schema"
    return rows, None


def _verify_imports(
    desired: DesiredState, rows: Sequence[Mapping[str, Any]]
) -> HarnessResult:
    installed: list[str] = []
    errors: list[str] = []
    drifted = False
    identity_error = False
    for contract in desired.all_contracts:
        matches = [row for row in rows if row.get("name") == contract.name]
        if not matches:
            errors.append(f"missing required plugin: {contract.name}")
            continue
        if len(matches) != 1:
            identity_error = True
            errors.append(f"plugin inventory is ambiguous for {contract.name}")
            continue
        row = matches[0]
        installed.append(contract.name)
        source = row.get("source")
        if not isinstance(source, str):
            identity_error = True
            errors.append(f"plugin {contract.name} source must be a string")
        elif source != _MARKETPLACE:
            identity_error = True
            errors.append(
                redact_text(
                    f"plugin {contract.name} expected source {_MARKETPLACE}, "
                    f"found {source}"
                )
            )
        version = row.get("version")
        if version is not None and version != contract.version:
            drifted = True
            errors.append(
                redact_text(
                    f"plugin {contract.name} expected {contract.version}, found {version}"
                )
            )
        components = row.get("components")
        if not isinstance(components, list) or "skills" not in components:
            identity_error = True
            errors.append(f"plugin {contract.name} does not expose native skills")
    state = ResultState.READY
    if errors:
        state = (
            ResultState.DRIFTED
            if drifted
            and not identity_error
            and len(installed) == len(desired.all_contracts)
            else ResultState.BLOCKED
        )
    return HarnessResult("antigravity", state, tuple(installed), {}, tuple(errors))


def _receipt_plugin_ids(
    receipt: HarnessReceipt,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids: list[str] = []
    errors: list[str] = []
    for identifier in receipt.plugin_ids:
        if identifier not in PORTABLE_BUNDLES:
            errors.append(f"receipt contains non-canonical plugin ID: {identifier}")
        elif identifier not in ids:
            ids.append(identifier)
    return tuple(ids), tuple(errors)


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "antigravity", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )
