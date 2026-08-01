"""Cursor native marketplace adapter."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from manifest_agent.adapters.base import (
    Detection,
    combine_results,
    native_command_result,
    normalize_component_identity,
    verify_declared_components,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

_ADAPTER_VERSION = "1"
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


class CursorAdapter:
    """Index Manifest in Cursor without inventing an activation mechanism."""

    name = "cursor"
    executable = "cursor-agent"
    adapter_version = _ADAPTER_VERSION

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        which: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self._which = which
        self._env = env

    def detect(self) -> Detection:
        """Report Cursor Agent availability and its native version."""
        executable = self._which(self.executable)
        if executable is None:
            return Detection(False, None, None, "cursor-agent CLI not present")
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
        """Verify the immutable user marketplace and documented plugin inventory."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        command, error = self._execute(
            (
                self.executable,
                "plugin",
                "marketplace",
                "list",
                "--format",
                "json",
            )
        )
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        row, parse_error = _marketplace_row(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        identity_error = _identity_error(desired, row)
        if identity_error is not None:
            return _blocked(identity_error)
        marketplace = HarnessResult(
            self.name,
            ResultState.READY,
            (),
            {"marketplace:manifest": "verified"},
        )
        plugins, evidence = _verify_inventory(desired, row, self._which)
        components = verify_declared_components(self.name, desired, evidence)
        activation = HarnessResult(
            self.name,
            ResultState.DEGRADED,
            (),
            {"plugins.activation": "unsupported"},
            errors=("Cursor exposes no native user-scope plugin activation API",),
        )
        return combine_results(marketplace, plugins, components, activation)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Index the exact recorded Git commit and report activation truthfully."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        command, error = self._execute(
            (
                self.executable,
                "plugin",
                "marketplace",
                "add",
                desired.repository_url,
                "--git-ref",
                desired.source_commit,
            )
        )
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        return self.inspect(desired)

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove only the singular marketplace URL owned by the receipt."""
        if receipt.harness != self.name:
            return _blocked(
                f"receipt harness {receipt.harness!r} does not match {self.name!r}"
            )
        if tuple(receipt.plugin_ids) != DOMAIN_BUNDLES:
            return _blocked("receipt must contain the exact nine canonical domains")
        marketplace_urls = tuple(
            entry.identifier
            for entry in receipt.owned_entries
            if entry.kind == "marketplace" and _is_url(entry.identifier)
        )
        if len(marketplace_urls) != 1:
            return _blocked("receipt must contain exactly one owned marketplace URL")
        command, error = self._execute(
            (
                self.executable,
                "plugin",
                "marketplace",
                "remove",
                marketplace_urls[0],
            )
        )
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        return HarnessResult(self.name, ResultState.READY, (), {})

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
        return _blocked("desired plugin versions must be non-empty")
    if not _COMMIT.fullmatch(desired.source_commit):
        return _blocked("Cursor marketplace commit must be immutable")
    if not _is_url(desired.repository_url):
        return _blocked("Cursor marketplace repository URL is invalid")
    if desired.source_dirty:
        return _blocked("Cursor cannot index a dirty local source checkout")
    if (
        desired.marketplace_source.kind is MarketplaceSourceKind.GIT
        and desired.marketplace_source.ref != desired.source_commit
    ):
        return _blocked("desired marketplace ref must match the release commit")
    return None


def _marketplace_row(
    stdout: str,
) -> tuple[Mapping[str, Any], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return {}, "Cursor marketplace list did not return valid JSON"
    if not isinstance(document, list) or any(
        not isinstance(row, dict) for row in document
    ):
        return {}, "Cursor marketplace list JSON has an invalid schema"
    matches = [row for row in document if row.get("name") == "manifest"]
    if len(matches) != 1:
        return {}, "Cursor marketplace list must contain exactly one manifest source"
    return matches[0], None


def _identity_error(desired: DesiredState, row: Mapping[str, Any]) -> str | None:
    observed_url = row.get("gitUrl")
    if not isinstance(observed_url, str) or _normalized_url(
        observed_url
    ) != _normalized_url(desired.repository_url):
        return (
            "Cursor marketplace source mismatch: expected "
            f"{desired.repository_url}, found {observed_url}"
        )
    observed_ref = row.get("gitRef")
    if observed_ref != desired.source_commit:
        return (
            "Cursor marketplace ref mismatch: expected "
            f"{desired.source_commit}, found {observed_ref}"
        )
    if row.get("scope") != "user":
        return "Cursor Manifest marketplace is not indexed at user scope"
    return None


def _verify_inventory(
    desired: DesiredState,
    marketplace: Mapping[str, Any],
    which: Callable[[str], str | None],
) -> tuple[HarnessResult, set[str]]:
    raw_plugins = marketplace.get("plugins")
    if not isinstance(raw_plugins, list) or any(
        not isinstance(row, dict) for row in raw_plugins
    ):
        return _blocked(
            "Cursor marketplace JSON lacks documented plugin inventory"
        ), set()
    rows: Sequence[Mapping[str, Any]] = raw_plugins
    by_name = {row.get("name"): row for row in rows if isinstance(row.get("name"), str)}
    installed: list[str] = []
    errors: list[str] = []
    evidence: set[str] = set()
    drifted = False
    for contract in desired.contracts:
        row = by_name.get(contract.name)
        if row is None:
            errors.append(f"missing indexed Cursor plugin: {contract.name}")
            continue
        installed.append(contract.name)
        if row.get("version") != contract.version:
            drifted = True
            errors.append(
                redact_text(
                    f"Cursor plugin {contract.name} expected {contract.version}, "
                    f"found {row.get('version')}"
                )
            )
        evidence.update(_inventory_evidence(contract.name, row))
        for tier in CapabilityTier:
            evidence.update(
                normalize_component_identity(contract.name, "executable", executable)
                for executable in contract.capabilities.executables[tier]
                if which(executable) is not None
            )
    state = ResultState.READY
    if errors:
        state = (
            ResultState.DRIFTED
            if drifted and len(installed) == len(desired.contracts)
            else ResultState.BLOCKED
        )
    return HarnessResult("cursor", state, tuple(installed), {}, tuple(errors)), evidence


def _inventory_evidence(bundle: str, row: Mapping[str, Any]) -> set[str]:
    evidence: set[str] = set()
    fields = {
        "skills": "skill",
        "subagents": "agent",
        "hooks": "hook",
        "runtime": "runtime",
        "rules": "guidance",
        "mcpServers": "mcp",
        "executables": "executable",
    }
    for field, kind in fields.items():
        values = row.get(field)
        if isinstance(values, Mapping):
            identifiers = (key for key in values if isinstance(key, str))
        elif isinstance(values, list):
            identifiers = (
                _inventory_identifier(value)
                for value in values
                if isinstance(value, str)
            )
        else:
            continue
        evidence.update(
            normalize_component_identity(bundle, kind, identifier)
            for identifier in identifiers
            if identifier
        )
    return evidence


def _inventory_identifier(value: str) -> str:
    path = Path(value)
    if path.name in {"SKILL.md", "plugin.json"}:
        return path.parent.name
    return path.stem


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.removesuffix("/").removesuffix(".git")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _is_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"https", "ssh"} and bool(parsed.netloc)


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "cursor", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )
