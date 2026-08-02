"""Devin CLI native plugin adapter."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.adapters.base import (
    CapabilityAdapterMixin,
    Detection,
    combine_results,
    native_command_result,
    normalize_component_identity,
    verify_declared_components,
)
from manifest_agent.adapters.devin_lifecycle import blocked as _blocked
from manifest_agent.adapters.devin_lifecycle import uninstall_devin
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
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PLUGIN_ID_PATTERN = r"(?:[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*"
_PLUGIN_ID = re.compile(_PLUGIN_ID_PATTERN)
_PLUGIN_VERSION_PATTERN = r"(?:v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?|unversioned)"
_LIST_ROW = re.compile(
    rf"^(?P<name>{_PLUGIN_ID_PATTERN})\s+"
    rf"(?P<version>{_PLUGIN_VERSION_PATTERN})(?:\s+.*)?$",
    re.IGNORECASE,
)
_LIST_SEPARATOR = re.compile(r"^[+|│─━═┄┈╌╍┅┉┴┬┼= _-]+$")
_LIST_HEADINGS = frozenset(
    {"installed", "plugin", "plugins", "name", "version", "blocked", "status"}
)


class DevinAdapter(CapabilityAdapterMixin):
    """Install and verify acquired generic bundle views without Claude inheritance."""

    name = "devin"
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
        """Report Devin CLI availability and its native version."""
        executable = self._which(self.name)
        if executable is None:
            return Detection(False, None, None, "devin CLI not present")
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
        """Verify native plugin versions, source identities, and discovered skills."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        list_command, error = self._execute((self.name, "plugins", "list"))
        if error is not None:
            return error
        assert list_command is not None
        if list_command.returncode != 0:
            return native_command_result(
                self.name, list_command, CapabilityTier.REQUIRED
            )
        installed_ids, parse_error = _list_plugin_ids(list_command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)

        failures: list[HarnessResult] = []
        info_rows: dict[str, Mapping[str, Any]] = {}
        for contract in desired.contracts:
            command, error = self._execute(
                (self.name, "plugins", "info", contract.name)
            )
            if error is not None:
                failures.append(error)
                continue
            assert command is not None
            if command.returncode != 0:
                failures.append(
                    native_command_result(self.name, command, CapabilityTier.REQUIRED)
                )
                continue
            row, info_error = _parse_info(command.stdout)
            if info_error is not None:
                failures.append(_blocked(f"{contract.name}: {info_error}"))
                continue
            info_rows[contract.name] = row

        plugins = _verify_plugins(desired, installed_ids, info_rows)
        evidence = _component_evidence(desired, info_rows, self._which)
        components = verify_declared_components(self.name, desired, evidence)
        inspected = combine_results(plugins, components)
        return combine_results(*failures, inspected) if failures else inspected

    def install(self, desired: DesiredState) -> HarnessResult:
        """Install every checksum-verified local bundle view non-interactively."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        failures: list[HarnessResult] = []
        already_present: list[HarnessResult] = []
        for contract in desired.contracts:
            command, error = self._execute(
                (
                    self.name,
                    "plugins",
                    "install",
                    str(desired.bundle_path(contract.name)),
                    "--yes",
                )
            )
            if error is not None:
                failures.append(error)
            elif command is not None and command.returncode != 0:
                result = native_command_result(
                    self.name, command, CapabilityTier.REQUIRED
                )
                (already_present if _already_present(command) else failures).append(
                    result
                )
        capabilities = self.install_capabilities(desired)
        inspected = self.inspect(desired)
        if set(inspected.installed_plugin_ids) != set(DOMAIN_BUNDLES):
            failures.extend(already_present)
        return combine_results(*failures, capabilities, inspected)

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove receipt plugins and prune only after proving unowned safety."""
        return uninstall_devin(self, receipt)

    def _list_installed(self) -> tuple[set[str] | None, HarnessResult | None]:
        command, error = self._execute((self.name, "plugins", "list"))
        if error is not None:
            return None, error
        assert command is not None
        if command.returncode != 0:
            return None, native_command_result(
                self.name, command, CapabilityTier.REQUIRED
            )
        plugin_ids, parse_error = _list_plugin_ids(command.stdout)
        if parse_error is not None:
            return None, _blocked(parse_error)
        return plugin_ids, None

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
    errors = _generic_view_errors(desired)
    if errors:
        return _blocked("invalid generic plugin view: " + "; ".join(errors))
    return None


def _generic_view_errors(desired: DesiredState) -> list[str]:
    errors: list[str] = []
    for contract in desired.contracts:
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
        surface = harnesses.get("devin") if isinstance(harnesses, Mapping) else None
        expected_skills = _expected_skill_paths(desired, contract.name)
        if (
            not expected_skills
            or document.get("name") != contract.name
            or document.get("version") != contract.version
            or document.get("skills") != list(expected_skills)
            or not isinstance(surface, Mapping)
            or surface.get("mode") != "native"
            or surface.get("skills") != list(expected_skills)
        ):
            errors.append(f"{contract.name} does not match its selected contract")
    return errors


def _expected_skill_paths(desired: DesiredState, bundle: str) -> tuple[str, ...]:
    contract = next(item for item in desired.contracts if item.name == bundle)
    bundle_root = desired.bundle_path(bundle)
    skills_root = bundle_root / contract.components.skills_root
    return tuple(
        sorted(
            {
                str(path.parent.relative_to(bundle_root))
                for pattern in contract.components.skills_include
                for path in skills_root.glob(pattern)
                if path.is_file()
            }
        )
    )


def _list_plugin_ids(stdout: str) -> tuple[set[str], str | None]:
    plain = _ANSI.sub("", stdout).strip()
    if not plain:
        return set(), "devin plugins list returned an empty inventory"
    plugin_ids: set[str] = set()
    saw_empty_inventory = False
    for line_number, raw_line in enumerate(plain.splitlines(), start=1):
        line = _normalized_list_line(raw_line)
        if not line:
            continue
        if line.lower() == "no plugins installed.":
            saw_empty_inventory = True
            continue
        if _is_list_header(line) or _LIST_SEPARATOR.fullmatch(line):
            continue
        match = _LIST_ROW.fullmatch(line)
        if match is None:
            return (
                set(),
                f"devin plugins list contains an unrecognized inventory row "
                f"at line {line_number}",
            )
        plugin_ids.add(match.group("name"))
    if saw_empty_inventory and plugin_ids:
        return set(), "devin plugins list returned a contradictory inventory"
    if saw_empty_inventory:
        return set(), None
    if not plugin_ids:
        return set(), "devin plugins list returned no parseable inventory rows"
    return plugin_ids, None


def _normalized_list_line(raw_line: str) -> str:
    line = raw_line.strip()
    if _LIST_SEPARATOR.fullmatch(line):
        return line
    line = line.strip("|│ ").lstrip("?*+!•├└ ").strip()
    return " ".join(line.replace("│", " ").replace("|", " ").split())


def _is_list_header(line: str) -> bool:
    lowered = line.lower().rstrip(":")
    if lowered == "installed plugins":
        return True
    words = set(lowered.split())
    return (
        bool(words)
        and words <= _LIST_HEADINGS
        and bool(words & {"name", "plugin", "plugins"})
    )


def _parse_info(stdout: str) -> tuple[Mapping[str, Any], str | None]:
    plain = _ANSI.sub("", stdout)
    row: dict[str, Any] = {"skills": set()}
    in_skills = False
    for raw_line in plain.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        key, separator, value = stripped.partition(":")
        field = key.lower()
        if separator and field in {"plugin", "version", "source"}:
            row["name" if field == "plugin" else field] = value.strip()
            in_skills = False
            continue
        header = lowered.rstrip(":")
        if header == "skills":
            in_skills = True
            continue
        if header in {"required plugins", "optional plugins", "forbidden plugins"}:
            in_skills = False
            continue
        if not in_skills or lowered == "(none)":
            continue
        skill = stripped.lstrip("-*+ ").split(maxsplit=1)[0]
        if _PLUGIN_ID.fullmatch(skill):
            row["skills"].add(skill)
    if any(not row.get(field) for field in ("name", "version", "source")):
        return {}, "devin plugins info omitted name, version, or source"
    return row, None


def _verify_plugins(
    desired: DesiredState,
    installed_ids: set[str],
    info_rows: Mapping[str, Mapping[str, Any]],
) -> HarnessResult:
    installed: list[str] = []
    errors: list[str] = []
    drifted = False
    identity_error = False
    for contract in desired.contracts:
        if contract.name not in installed_ids:
            errors.append(f"missing required plugin: {contract.name}")
            continue
        installed.append(contract.name)
        row = info_rows.get(contract.name)
        if row is None:
            errors.append(f"missing native plugin info: {contract.name}")
            continue
        if row.get("name") != contract.name:
            identity_error = True
            errors.append(f"plugin info identity mismatch for {contract.name}")
        version = row.get("version")
        if version != contract.version:
            drifted = True
            errors.append(
                redact_text(
                    f"plugin {contract.name} expected {contract.version}, found {version}"
                )
            )
        source = row.get("source")
        if not isinstance(source, str) or _resolved_path(source) != _resolved_path(
            str(desired.bundle_path(contract.name))
        ):
            identity_error = True
            errors.append(f"plugin {contract.name} source mismatch")
    state = ResultState.READY
    if errors:
        state = (
            ResultState.DRIFTED
            if drifted
            and not identity_error
            and len(installed) == len(desired.contracts)
            and len(info_rows) == len(desired.contracts)
            else ResultState.BLOCKED
        )
    return HarnessResult("devin", state, tuple(installed), {}, tuple(errors))


def _component_evidence(
    desired: DesiredState,
    info_rows: Mapping[str, Mapping[str, Any]],
    which: Callable[[str], str | None],
) -> set[str]:
    evidence: set[str] = set()
    for contract in desired.contracts:
        row = info_rows.get(contract.name)
        skills = row.get("skills") if row is not None else ()
        if isinstance(skills, set):
            evidence.update(
                normalize_component_identity(contract.name, "skill", skill)
                for skill in skills
            )
        for tier in CapabilityTier:
            evidence.update(
                normalize_component_identity(contract.name, "executable", executable)
                for executable in contract.capabilities.executables[tier]
                if which(executable) is not None
            )
    return evidence


def _resolved_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _already_present(command: CommandResult) -> bool:
    diagnostic = f"{command.stdout}\n{command.stderr}".lower()
    return "already" in diagnostic and any(
        word in diagnostic for word in ("installed", "exists", "present", "up to date")
    )
