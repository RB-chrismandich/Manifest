"""Cursor native marketplace adapter."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from manifest_agent.adapters.base import (
    CapabilityAdapterMixin,
    Detection,
    NativeMcpInventory,
    combine_results,
    native_command_result,
    normalize_native_mcp_inventory,
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
from manifest_agent.release import REPOSITORY_URL

_ADAPTER_VERSION = "1"
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_OWNERSHIP_MARKER = "manifest"


class CursorAdapter(CapabilityAdapterMixin):
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
        repository_url: str = REPOSITORY_URL,
        native_mcp_inventory: NativeMcpInventory = (),
    ) -> None:
        self.runner = runner or CommandRunner()
        self._which = which
        self._env = env
        self._repository_url = repository_url
        self._native_mcp_inventory = normalize_native_mcp_inventory(
            native_mcp_inventory
        )

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
        return combine_results(marketplace, self._inspect_plugin_support())

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
        capabilities = self.install_capabilities(desired)
        return combine_results(capabilities, self.inspect(desired))

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove only the singular marketplace URL owned by the receipt."""
        invalid = self.validate_uninstall_receipt(
            receipt, receipt.plugin_ids, DOMAIN_BUNDLES
        )
        if invalid is not None:
            return invalid
        if not _is_url(self._repository_url):
            return _blocked("configured Manifest repository URL is invalid")
        marketplace_urls = tuple(
            entry.identifier
            for entry in receipt.owned_entries
            if entry.kind == "marketplace"
            and entry.ownership_marker == _OWNERSHIP_MARKER
            and _is_url(entry.identifier)
            and _normalized_url(entry.identifier)
            == _normalized_url(self._repository_url)
        )
        if len(marketplace_urls) != 1:
            return _blocked(
                "receipt must contain exactly one owned marketplace URL with the "
                "Manifest marker and canonical repository identity"
            )
        capabilities = self.remove_capabilities(receipt)
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
            return combine_results(capabilities, error)
        assert command is not None
        if command.returncode != 0:
            failure = native_command_result(self.name, command, CapabilityTier.REQUIRED)
            return combine_results(capabilities, failure)
        success = HarnessResult(self.name, ResultState.READY, (), {})
        return combine_results(capabilities, success)

    def _inspect_plugin_support(self) -> HarnessResult:
        command, error = self._execute((self.executable, "plugin", "--help"))
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        commands = _documented_plugin_commands(command.stdout)
        if commands == {"marketplace"}:
            return _unsupported_plugins(
                (
                    "Cursor plugin help exposes marketplace management only; "
                    "no documented user-scope plugin inventory or activation API",
                )
            )
        if not commands:
            return _blocked(
                "Cursor plugin help did not expose a valid command inventory"
            )
        return _blocked(
            "Cursor exposes new native plugin commands that require adapter support "
            "before inventory can be verified"
        )

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
    if (
        not isinstance(observed_url, str)
        or not _is_url(observed_url)
        or _normalized_url(observed_url) != _normalized_url(desired.repository_url)
    ):
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


def _documented_plugin_commands(stdout: str) -> set[str]:
    commands: set[str] = set()
    in_commands = False
    for line in stdout.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if not in_commands or not line.startswith("  "):
            continue
        command = line.strip().split(maxsplit=1)[0]
        if command:
            commands.add(command)
    return commands


def _unsupported_plugins(errors: Sequence[str]) -> HarnessResult:
    return HarnessResult(
        "cursor",
        ResultState.DEGRADED,
        (),
        {
            "plugins.inventory": "unsupported",
            "plugins.activation": "unsupported",
        },
        errors=tuple(redact_text(error) for error in errors),
    )


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.removesuffix("/").removesuffix(".git")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _is_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"https", "ssh"}
        and bool(parsed.netloc)
        and not parsed.query
        and not parsed.fragment
    )


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "cursor", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )
