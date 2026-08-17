"""Receipt-authorized resumable Codex uninstallation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from manifest_agent.adapters.base import combine_results
from manifest_agent.adapters.codex_catalog import (
    authenticated_catalog,
    authenticated_marketplace,
    observe_restoration,
    owns_marketplace,
    receipt_plugin_ids,
)
from manifest_agent.adapters.codex_common import MARKETPLACE, blocked
from manifest_agent.adapters.codex_uninstall_state import (
    checkpoint_uninstall,
    load_or_create_uninstall_saga,
    uninstall_saga_path,
)
from manifest_agent.codex_config import (
    CodexConfigError,
    plugin_enabled_change_from_metadata,
    rollback_plugin_enabled,
)
from manifest_agent.codex_skill_cutover import SkillCutoverError, restore_codex_skills
from manifest_agent.models import (
    AdapterMarketplaceState,
    HarnessReceipt,
    HarnessResult,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import codex_receipt_ownership_errors
from manifest_agent.state import _fsync_directory


@dataclass
class _UninstallRun:
    receipt: HarnessReceipt
    plugin_ids: tuple[str, ...]
    saga_path: Path
    saga: dict[str, Any]
    failures: list[HarnessResult]


class CodexUninstallMixin:
    """Remove only receipt-owned Codex state through a durable saga."""

    if TYPE_CHECKING:
        name: str
        _env: Mapping[str, str] | None
        _which: Callable[[str], str | None]
        _last_marketplace_identity: AdapterMarketplaceState | None
        _marketplace_observed: bool
        _list_installed_manifest_ids: Callable[
            [], tuple[set[str] | None, HarnessResult | None]
        ]
        _list_installed_manifest_rows: Callable[
            [], tuple[dict[str, Mapping[str, Any]] | None, HarnessResult | None]
        ]
        _observed_marketplace_identity: Callable[..., AdapterMarketplaceState | None]
        _run_json_mutations: Callable[[Sequence[Sequence[str]]], list[HarnessResult]]
        remove_capabilities: Callable[[HarnessReceipt], HarnessResult]
        validate_uninstall_receipt: Callable[..., HarnessResult | None]

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Resume a durable receipt-authorized uninstall saga."""
        run, failure = _prepare_uninstall(self, receipt)
        if failure is not None or run is None:
            return failure or blocked("Codex uninstall preparation failed")
        restoration = _restore_owned_state(run)
        if restoration is not None:
            return restoration
        capabilities = _remove_capabilities(self, run)
        if capabilities.state not in {ResultState.READY, ResultState.DEGRADED}:
            return capabilities
        plugin_failure = _remove_owned_plugins(self, run, capabilities)
        if plugin_failure is not None:
            return plugin_failure
        installed_ids, list_error = self._list_installed_manifest_ids()
        if list_error is not None or installed_ids is None:
            return combine_results(
                capabilities,
                *run.failures,
                list_error or blocked("Codex plugin inventory is unavailable"),
            )
        plugins = _finish_uninstall(self, run, installed_ids)
        result = combine_results(capabilities, plugins)
        if result.state is ResultState.READY:
            run.saga_path.unlink(missing_ok=True)
            if run.saga_path.parent.exists():
                _fsync_directory(run.saga_path.parent)
        return result

    def _observe_capability_removal(self, receipt: HarnessReceipt) -> str:
        owned_graphify = any(
            entry.kind == "executable" and entry.identifier == "graphify"
            for entry in receipt.owned_entries
        )
        if not owned_graphify:
            return "completed"
        try:
            return "unapplied" if self._which("graphify") else "completed"
        # constitution: exempt C-ERR — an injected executable probe failure is ambiguous.
        except Exception:
            return "ambiguous"


def _prepare_uninstall(
    adapter: CodexUninstallMixin, receipt: HarnessReceipt
) -> tuple[_UninstallRun | None, HarnessResult | None]:
    receipt_errors = codex_receipt_ownership_errors(receipt, env=adapter._env)
    if receipt_errors:
        return None, blocked("; ".join(receipt_errors))
    expected = authenticated_marketplace(receipt, adapter._env)
    if expected is None:
        return None, blocked("receipt Codex marketplace ownership proof is invalid")
    try:
        observed = adapter._observed_marketplace_identity(allow_absent=True)
    except ValueError as error:
        return None, blocked(str(error))
    if observed is not None and observed != expected:
        return None, blocked("Codex marketplace source was replaced before uninstall")
    plugin_ids, id_errors = receipt_plugin_ids(receipt, adapter._env)
    # Codex's canonical inventory is its own signed catalog snapshot, not the
    # static bundle list: a release may legitimately carry bundles this build
    # does not know. Deriving the expected set from the authenticated catalog
    # keeps the completeness check real instead of comparing plugin_ids to
    # itself, which can never fail.
    authenticated = authenticated_catalog(receipt, adapter._env)
    expected_plugin_ids = (
        tuple(f"{row['name']}@{MARKETPLACE}" for row in authenticated)
        if authenticated is not None
        else ()
    )
    invalid = adapter.validate_uninstall_receipt(
        receipt,
        plugin_ids,
        expected_plugin_ids,
        identity_errors=id_errors,
        marketplace_identifier=MARKETPLACE,
    )
    if invalid is not None:
        return None, invalid
    saga_path = uninstall_saga_path(receipt, adapter._env)
    try:
        saga = load_or_create_uninstall_saga(saga_path, receipt, plugin_ids)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return None, blocked(f"Codex uninstall journal is invalid: {error}")
    return _UninstallRun(receipt, plugin_ids, saga_path, saga, []), None


def _restore_owned_state(run: _UninstallRun) -> HarnessResult | None:
    restorations = tuple(
        entry
        for entry in reversed(run.receipt.owned_entries)
        if entry.kind in {"codex-skill-source", "plugin-enabled-state"}
    )
    for index, entry in enumerate(restorations):
        step = f"restore:{index}:{entry.kind}:{entry.identifier}"
        if run.saga["steps"].get(step) == "done":
            continue
        observation = observe_restoration(entry)
        if observation == "completed":
            checkpoint_uninstall(run.saga_path, run.saga, step, "done")
            continue
        if observation == "ambiguous":
            return blocked(
                f"prepared {entry.kind} restoration has ambiguous native state"
            )
        if run.saga["steps"].get(step) != "prepared":
            checkpoint_uninstall(run.saga_path, run.saga, step, "prepared")
        failure = _restore_entry(entry)
        if failure is not None:
            return failure
        checkpoint_uninstall(run.saga_path, run.saga, step, "done")
    return None


def _restore_entry(entry: OwnedEntry) -> HarnessResult | None:
    try:
        if entry.kind == "codex-skill-source":
            restore_codex_skills(entry)
        elif entry.kind == "plugin-enabled-state" and entry.target_path:
            metadata = json.loads(entry.previous_checksum or "{}")
            rollback_plugin_enabled(
                Path(entry.target_path),
                plugin_enabled_change_from_metadata(entry.identifier, metadata),
            )
    except (
        CodexConfigError,
        SkillCutoverError,
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        return blocked(f"owned state restoration failed: {error}")
    return None


def _remove_capabilities(
    adapter: CodexUninstallMixin, run: _UninstallRun
) -> HarnessResult:
    step = "remove:capabilities"
    observation = adapter._observe_capability_removal(run.receipt)
    if observation == "ambiguous":
        return blocked("prepared capability removal has ambiguous native state")
    if observation == "completed":
        checkpoint_uninstall(run.saga_path, run.saga, step, "done")
        return HarnessResult(adapter.name, ResultState.READY, (), {})
    if run.saga["steps"].get(step) != "prepared":
        checkpoint_uninstall(run.saga_path, run.saga, step, "prepared")
    result = adapter.remove_capabilities(run.receipt)
    if result.state in {ResultState.READY, ResultState.DEGRADED}:
        checkpoint_uninstall(run.saga_path, run.saga, step, "done")
    return result


def _remove_owned_plugins(
    adapter: CodexUninstallMixin,
    run: _UninstallRun,
    capabilities: HarnessResult,
) -> HarnessResult | None:
    catalog = authenticated_catalog(run.receipt, adapter._env)
    if catalog is None:
        return blocked("receipt Codex catalog ownership proof does not match")
    versions = {f"{row['name']}@{MARKETPLACE}": row["version"] for row in catalog}
    for plugin_id in run.plugin_ids:
        step = f"remove:{plugin_id}"
        if run.saga["steps"].get(step) == "done":
            continue
        if run.saga["steps"].get(step) == "prepared":
            failure = _resume_prepared_removal(adapter, run, plugin_id, versions)
            if failure is not None:
                return combine_results(capabilities, *run.failures, failure)
            if run.saga["steps"].get(step) == "done":
                continue
        else:
            checkpoint_uninstall(run.saga_path, run.saga, step, "prepared")
        removal = adapter._run_json_mutations(
            [(adapter.name, "plugin", "remove", plugin_id, "--json")]
        )
        if removal:
            run.failures.extend(removal)
            return combine_results(capabilities, *run.failures)
        checkpoint_uninstall(run.saga_path, run.saga, step, "done")
    return None


def _resume_prepared_removal(
    adapter: CodexUninstallMixin,
    run: _UninstallRun,
    plugin_id: str,
    versions: Mapping[str, str],
) -> HarnessResult | None:
    rows, error = adapter._list_installed_manifest_rows()
    if error is not None or rows is None:
        return error or blocked("Codex plugin inventory is unavailable")
    row = rows.get(plugin_id)
    if row is None:
        checkpoint_uninstall(run.saga_path, run.saga, f"remove:{plugin_id}", "done")
        return None
    if row.get("version") != versions[plugin_id] or row.get("enabled") is False:
        return blocked(f"prepared plugin removal is ambiguous for {plugin_id}")
    return None


def _finish_uninstall(
    adapter: CodexUninstallMixin, run: _UninstallRun, installed_ids: set[str]
) -> HarnessResult:
    remaining = tuple(
        plugin_id for plugin_id in run.plugin_ids if plugin_id in installed_ids
    )
    unowned = sorted(installed_ids - set(run.plugin_ids))
    warnings: tuple[str, ...] = ()
    if unowned:
        warnings = (
            "manifest marketplace retained because an unowned plugin references it: "
            + ", ".join(unowned),
        )
    elif not remaining and not run.failures and owns_marketplace(run.receipt):
        marketplace_failure = _remove_owned_marketplace(adapter, run)
        if marketplace_failure is not None:
            return marketplace_failure
    result = HarnessResult(
        adapter.name,
        ResultState.BLOCKED if remaining else ResultState.READY,
        remaining,
        {},
        errors=tuple(
            f"receipt-owned plugin remains installed: {item}" for item in remaining
        ),
        warnings=warnings,
    )
    return combine_results(*run.failures, result) if run.failures else result


def _remove_owned_marketplace(
    adapter: CodexUninstallMixin, run: _UninstallRun
) -> HarnessResult | None:
    step = "remove:marketplace:manifest"
    expected = authenticated_marketplace(run.receipt, adapter._env)
    if expected is None:
        return blocked("receipt Codex marketplace ownership proof is invalid")
    observation = _prepare_marketplace_removal(adapter, run, step, expected)
    if observation is not None:
        return observation
    if run.saga["steps"].get(step) == "done":
        return None
    failures = adapter._run_json_mutations(
        [(adapter.name, "plugin", "marketplace", "remove", MARKETPLACE, "--json")]
    )
    run.failures.extend(failures)
    if failures:
        return None
    try:
        observed = adapter._observed_marketplace_identity(allow_absent=True)
    except ValueError as error:
        run.failures.append(blocked(str(error)))
    else:
        if observed is None:
            checkpoint_uninstall(run.saga_path, run.saga, step, "done")
        else:
            run.failures.append(
                blocked("Codex marketplace removal did not reach exact absence")
            )
    return None


def _prepare_marketplace_removal(
    adapter: CodexUninstallMixin,
    run: _UninstallRun,
    step: str,
    expected: AdapterMarketplaceState,
) -> HarnessResult | None:
    if run.saga["steps"].get(step) == "done":
        return None
    try:
        observed = (
            adapter._last_marketplace_identity
            if adapter._marketplace_observed
            else adapter._observed_marketplace_identity(allow_absent=True)
        )
    except ValueError as error:
        run.failures.append(blocked(str(error)))
        return combine_results(*run.failures)
    if observed is None:
        checkpoint_uninstall(run.saga_path, run.saga, step, "done")
    elif observed != expected:
        return combine_results(
            *run.failures,
            blocked(
                "prepared marketplace removal is ambiguous because "
                "the manifest source was replaced"
            ),
        )
    elif run.saga["steps"].get(step) != "prepared":
        checkpoint_uninstall(run.saga_path, run.saga, step, "prepared")
    return None
