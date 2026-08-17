"""Devin CLI native plugin adapter."""

from __future__ import annotations

import hashlib
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
from manifest_agent.adapters.devin_parsing import _list_plugin_ids, _parse_info
from manifest_agent.adapters.devin_view import _generic_view_errors
from manifest_agent.codex_plugin_backup import (
    capture_owned_file_backup,
    capture_plugin_backup,
    plugin_tree_sha256,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    AdapterPluginState,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import owned_file_entry, owned_file_ownership
from manifest_agent.process import CommandRunner, redact_text

_ADAPTER_VERSION = "1"
_ADHD_BUNDLE = "manifest-i-have-adhd"


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

    def _adhd_rule_path(self) -> Path:
        home = Path((self._env or {}).get("HOME", Path.home()))
        return home / ".codeium/windsurf/memories/global_rules.md"

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
        for contract in desired.all_contracts:
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
        evidence = _component_evidence(
            desired, info_rows, self._which, self._adhd_rule_path()
        )
        components = verify_declared_components(self.name, desired, evidence)
        inspected = combine_results(plugins, components)
        return combine_results(*failures, inspected) if failures else inspected

    def install(self, desired: DesiredState) -> HarnessResult:
        """Install every checksum-verified local bundle view non-interactively."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        prepared_rule, rule_error = _prepare_adhd_rule(
            desired, self._adhd_rule_path(), self._env
        )
        if rule_error is not None:
            return rule_error
        assert prepared_rule is not None
        failures: list[HarnessResult] = []
        already_present: list[HarnessResult] = []
        for contract in desired.all_contracts:
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
        rule = _apply_adhd_rule(self, prepared_rule)
        capabilities = self.install_capabilities(desired)
        inspected = self.inspect(desired)
        if set(inspected.installed_plugin_ids) != {
            contract.name for contract in desired.all_contracts
        }:
            failures.extend(already_present)
        return combine_results(*failures, rule, capabilities, inspected)

    def _native_reconcile_inventory(
        self,
        desired: DesiredState,
        *,
        capture_backups: bool,
        identifiers: set[str] | None = None,
    ) -> tuple[AdapterPluginState, ...]:
        command, error = self._execute((self.name, "plugins", "list"))
        if error is not None or command is None:
            raise ValueError("Devin plugin inventory is unavailable")
        installed, parse_error = _list_plugin_ids(command.stdout)
        if parse_error is not None:
            raise ValueError(parse_error)
        selected = identifiers or {contract.name for contract in desired.all_contracts}
        inventory = []
        for name in sorted(installed & selected):
            command, error = self._execute((self.name, "plugins", "info", name))
            if error is not None or command is None:
                raise ValueError(f"Devin plugin info is unavailable for {name}")
            row, info_error = _parse_info(command.stdout)
            if info_error is not None:
                raise ValueError(info_error)
            version = row.get("version")
            source = row.get("source")
            if not isinstance(version, str) or not isinstance(source, str):
                raise ValueError("Devin plugin inventory lacks exact native metadata")
            root = Path(source).resolve(strict=True)
            backup = None
            if capture_backups:
                backup = capture_plugin_backup(
                    {
                        "pluginId": name,
                        "version": version,
                        "enabled": True,
                        "source": {"path": str(root)},
                    },
                    self._env,
                    require_manifest_suffix=False,
                ).to_dict()
            inventory.append(
                AdapterPluginState(
                    name,
                    version,
                    True,
                    rollback_data=backup,
                    installed_path=str(root),
                    installed_sha256=plugin_tree_sha256(root),
                    source_identity=str(root),
                )
            )
        return tuple(inventory)

    def _expected_reconcile_source_identity(
        self, desired: DesiredState, bundle: str
    ) -> str:
        return str(desired.bundle_path(bundle).resolve(strict=False))

    def _expected_reconcile_owned_files_from_prior(
        self,
        prior: tuple[dict[str, object], ...],
        desired: DesiredState,
    ) -> tuple[dict[str, object], ...]:
        path = self._adhd_rule_path()
        unexpected = tuple(item for item in prior if item.get("path") != str(path))
        if unexpected:
            raise ValueError("Devin receipt contains an unsupported owned file target")
        source = desired.bundle_path(_ADHD_BUNDLE) / "devin/global-rule.md"
        if source.is_symlink() or not source.is_file():
            raise ValueError("generated Devin ADHD global rule is missing")
        backup, _source_mode, digest = capture_owned_file_backup(source, self._env)
        return (
            {
                "path": str(path),
                "type": "file",
                "mode": 0o600,
                "digest": digest,
                "restore": {"archive": backup.to_dict()},
            },
        )

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
        return _blocked("desired state must contain the exact canonical domains")
    if any(not contract.version for contract in desired.all_contracts):
        return _blocked("desired plugin versions must be non-empty")
    unsupported = [
        contract.compatibility["devin"].reason
        for contract in desired.all_contracts
        if contract.compatibility["devin"].mode == "unsupported"
    ]
    if unsupported:
        return _blocked("Devin delivery is unsupported: " + "; ".join(unsupported))
    errors = _generic_view_errors(desired)
    if errors:
        return _blocked("invalid generic plugin view: " + "; ".join(errors))
    return None


def _verify_plugins(
    desired: DesiredState,
    installed_ids: set[str],
    info_rows: Mapping[str, Mapping[str, Any]],
) -> HarnessResult:
    installed: list[str] = []
    errors: list[str] = []
    drifted = False
    identity_error = False
    for contract in desired.all_contracts:
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
            and len(installed) == len(desired.all_contracts)
            and len(info_rows) == len(desired.all_contracts)
            else ResultState.BLOCKED
        )
    return HarnessResult("devin", state, tuple(installed), {}, tuple(errors))


def _component_evidence(
    desired: DesiredState,
    info_rows: Mapping[str, Mapping[str, Any]],
    which: Callable[[str], str | None],
    rule_path: Path | None = None,
) -> set[str]:
    evidence: set[str] = set()
    for contract in desired.all_contracts:
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
        if contract.name == _ADHD_BUNDLE and rule_path is not None:
            generated = desired.bundle_path(contract.name) / "devin/global-rule.md"
            try:
                verified = generated.read_bytes() == rule_path.read_bytes()
            except OSError:
                verified = False
            if verified:
                for kind, components in (
                    ("guidance", contract.components.guidance),
                    ("hook", contract.components.hooks),
                    ("runtime", contract.components.runtime),
                ):
                    evidence.update(
                        normalize_component_identity(contract.name, kind, item.id)
                        for item in components
                    )
    return evidence


def _prepare_adhd_rule(
    desired: DesiredState, target: Path, env: Mapping[str, str] | None
) -> tuple[OwnedEntry | None, HarnessResult | None]:
    source = desired.bundle_path(_ADHD_BUNDLE) / "devin/global-rule.md"
    if source.is_symlink() or not source.is_file():
        return None, _blocked("generated Devin ADHD global rule is missing")
    try:
        source_backup, _source_mode, digest = capture_owned_file_backup(source, env)
        prior: dict[str, object]
        try:
            prior_backup, prior_mode, prior_digest = capture_owned_file_backup(
                target, env
            )
            prior = {
                "path": str(target),
                "type": "file",
                "mode": prior_mode,
                "digest": prior_digest,
                "restore": {"archive": prior_backup.to_dict()},
            }
            if (
                prior_digest != hashlib.sha256(b"").hexdigest()
                and prior_digest != digest
            ):
                return None, _blocked(
                    "Devin global_rules.md contains unowned user content"
                )
        except Exception:
            if target.exists() or target.is_symlink():
                return None, _blocked(
                    "Devin global_rules.md is not a safe regular file"
                )
            prior = {"path": str(target), "type": "missing"}
        installed = {
            "path": str(target),
            "type": "file",
            "mode": 0o600,
            "digest": digest,
            "restore": {"archive": source_backup.to_dict()},
        }
        entry = owned_file_entry(
            "devin-global-rules", target, prior, installed, env=env
        )
    except (OSError, ValueError):
        return None, _blocked("could not prepare Devin ADHD global rule")
    return entry, None


def _apply_adhd_rule(adapter: DevinAdapter, entry: OwnedEntry) -> HarnessResult:
    prior, installed, errors = owned_file_ownership(entry, env=adapter._env)
    if errors or prior is None or installed is None or entry.target_path is None:
        return _blocked("could not validate prepared Devin ADHD global rule")
    try:
        with adapter._owned_file_mutation_lock():
            adapter._conditional_owned_file_transition(
                Path(entry.target_path), prior, installed
            )
    except (OSError, ValueError):
        return _blocked("could not install Devin ADHD global rule")
    return HarnessResult("devin", ResultState.READY, (), {}, owned_entries=(entry,))


def _resolved_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _already_present(command: CommandResult) -> bool:
    diagnostic = f"{command.stdout}\n{command.stderr}".lower()
    return "already" in diagnostic and any(
        word in diagnostic for word in ("installed", "exists", "present", "up to date")
    )
