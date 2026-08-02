"""Gemini CLI native extension adapter."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.adapters.base import (
    CapabilityAdapterMixin,
    Detection,
    NativeMcpInventory,
    collect_native_component_evidence,
    combine_results,
    native_command_result,
    normalize_component_identity,
    normalize_native_mcp_inventory,
    verify_declared_components,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

_ADAPTER_VERSION = "1"


class GeminiAdapter(CapabilityAdapterMixin):
    """Install and verify bundle-local Gemini extensions."""

    name = "gemini"
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
        """Report Gemini CLI availability and its native version."""
        executable = self._which(self.name)
        if executable is None:
            return Detection(False, None, None, "gemini CLI not present")
        command, error = self._execute((executable, "--version"))
        if error is not None:
            return Detection(True, executable, None, error.errors[0])
        assert command is not None
        if command.returncode != 0:
            result = native_command_result(self.name, command, CapabilityTier.REQUIRED)
            return Detection(True, executable, None, result.errors[0])
        version = command.stdout.strip().splitlines()
        return Detection(
            True,
            executable,
            redact_text(version[0]) if version else None,
        )

    def inspect(self, desired: DesiredState) -> HarnessResult:
        """Require native extension versions and all declared component evidence."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        extension_command, error = self._execute(
            (self.name, "extensions", "list", "--output-format", "json")
        )
        if error is not None:
            return error
        assert extension_command is not None
        if extension_command.returncode != 0:
            return native_command_result(
                self.name, extension_command, CapabilityTier.REQUIRED
            )
        rows, parse_error = _extension_rows(extension_command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        extensions = _verify_extensions(desired, rows)

        skills_command, error = self._execute((self.name, "skills", "list", "--all"))
        if error is not None:
            return combine_results(extensions, error)
        assert skills_command is not None
        if skills_command.returncode != 0:
            failure = native_command_result(
                self.name, skills_command, CapabilityTier.REQUIRED
            )
            return combine_results(extensions, failure)
        evidence = _component_evidence(
            desired, rows, skills_command.stdout, self._which
        )
        components = verify_declared_components(self.name, desired, evidence)
        return combine_results(extensions, components)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Install each verified bundle without enabling native auto-update."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        failures: list[HarnessResult] = []
        for contract in desired.contracts:
            command, error = self._execute(
                (
                    self.name,
                    "extensions",
                    "install",
                    str(desired.bundle_path(contract.name)),
                    "--consent",
                    "--skip-settings",
                )
            )
            if error is not None:
                failures.append(error)
            elif command is not None and command.returncode != 0:
                failures.append(
                    native_command_result(self.name, command, CapabilityTier.REQUIRED)
                )
        capabilities = self.install_capabilities(desired)
        inspected = self.inspect(desired)
        return combine_results(*failures, capabilities, inspected)

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Uninstall only canonical extension names recorded by the receipt."""
        if receipt.harness != self.name:
            return _blocked(
                f"receipt harness {receipt.harness!r} does not match {self.name!r}"
            )
        capabilities = self.remove_capabilities(receipt)
        plugin_ids, id_errors = _receipt_plugin_ids(receipt)
        failures = [_blocked(error) for error in id_errors]
        for plugin_id in plugin_ids:
            command, error = self._execute(
                (self.name, "extensions", "uninstall", plugin_id)
            )
            if error is not None:
                failures.append(error)
            elif command is not None and command.returncode != 0:
                failures.append(
                    native_command_result(self.name, command, CapabilityTier.REQUIRED)
                )
        success = HarnessResult(self.name, ResultState.READY, (), {})
        return combine_results(capabilities, *failures, success)

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
        return _blocked("desired state must contain the exact nine canonical domains")
    if any(not contract.version for contract in desired.contracts):
        return _blocked("desired extension versions must be non-empty")
    missing = [
        contract.name
        for contract in desired.contracts
        if not desired.bundle_path(contract.name).is_dir()
    ]
    if missing:
        return _blocked(
            "verified release is missing bundle directories: " + ", ".join(missing)
        )
    return None


def _extension_rows(
    stdout: str,
) -> tuple[list[Mapping[str, Any]], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return [], "Gemini extension list did not return valid JSON"
    if not isinstance(document, list) or any(
        not isinstance(row, dict) for row in document
    ):
        return [], "Gemini extension list JSON has an invalid schema"
    return document, None


def _verify_extensions(
    desired: DesiredState, rows: Sequence[Mapping[str, Any]]
) -> HarnessResult:
    by_name = {row.get("name"): row for row in rows if isinstance(row.get("name"), str)}
    installed: list[str] = []
    errors: list[str] = []
    drifted = False
    inactive = False
    for contract in desired.contracts:
        row = by_name.get(contract.name)
        if row is None:
            errors.append(f"missing required extension: {contract.name}")
            continue
        installed.append(contract.name)
        version = row.get("version")
        if version != contract.version:
            drifted = True
            errors.append(
                redact_text(
                    f"extension {contract.name} expected {contract.version}, found {version}"
                )
            )
        if row.get("isActive") is not True:
            inactive = True
            errors.append(f"extension {contract.name} is inactive")
    state = ResultState.READY
    if errors:
        state = (
            ResultState.DRIFTED
            if drifted and not inactive and len(installed) == len(desired.contracts)
            else ResultState.BLOCKED
        )
    return HarnessResult("gemini", state, tuple(installed), {}, tuple(errors))


def _component_evidence(
    desired: DesiredState,
    rows: Sequence[Mapping[str, Any]],
    skills_stdout: str,
    which: Callable[[str], str | None],
) -> set[str]:
    roots: dict[str, Path] = {}
    mcp_servers: dict[str, tuple[str, ...]] = {}
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or name not in DOMAIN_BUNDLES:
            continue
        root = _extension_root(row)
        if root is not None:
            roots[name] = root
        native_mcp = row.get("mcpServers")
        if isinstance(native_mcp, Mapping):
            mcp_servers[name] = tuple(key for key in native_mcp if isinstance(key, str))
    evidence = collect_native_component_evidence(desired, roots, mcp_servers, which)
    evidence = {item for item in evidence if ":skill:" not in item}
    for skill, location in _skill_rows(skills_stdout):
        for bundle, root in roots.items():
            if _is_within(location, root):
                evidence.add(normalize_component_identity(bundle, "skill", skill))
    return evidence


def _extension_root(row: Mapping[str, Any]) -> Path | None:
    for key in ("path", "extensionPath", "installPath"):
        value = row.get(key)
        if isinstance(value, str):
            return Path(value)
    metadata = row.get("installMetadata")
    if isinstance(metadata, Mapping):
        for key in ("path", "source"):
            value = metadata.get(key)
            if isinstance(value, str) and Path(value).is_absolute():
                return Path(value)
    return None


def _skill_rows(stdout: str) -> tuple[tuple[str, Path], ...]:
    rows: list[tuple[str, Path]] = []
    skill: str | None = None
    for line in stdout.splitlines():
        if line and not line[0].isspace() and " [Enabled]" in line:
            skill = line.split(" [", 1)[0].strip()
        elif line and not line[0].isspace():
            skill = None
        elif skill is not None and line.lstrip().startswith("Location:"):
            location = line.split("Location:", 1)[1].strip()
            if location:
                rows.append((skill, Path(location)))
            skill = None
    return tuple(rows)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _receipt_plugin_ids(
    receipt: HarnessReceipt,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids: list[str] = []
    errors: list[str] = []
    for identifier in receipt.plugin_ids:
        if identifier not in DOMAIN_BUNDLES:
            errors.append(f"receipt contains non-canonical extension ID: {identifier}")
        elif identifier not in ids:
            ids.append(identifier)
    return tuple(ids), tuple(errors)


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "gemini", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )
