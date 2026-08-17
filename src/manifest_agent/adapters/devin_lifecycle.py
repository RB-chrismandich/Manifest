"""Receipt-owned Devin uninstall lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from manifest_agent.adapters.base import combine_results, native_command_result
from manifest_agent.adapters.capability_receipt import (
    expected_uninstall_plugin_ids,
)
from manifest_agent.contracts import PORTABLE_BUNDLES
from manifest_agent.models import (
    CapabilityTier,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import redact_text

if TYPE_CHECKING:
    from manifest_agent.adapters.devin import DevinAdapter
    from manifest_agent.models import OwnedEntry


def uninstall_devin(adapter: DevinAdapter, receipt: HarnessReceipt) -> HarnessResult:
    """Remove receipt plugins and prune only after proving unowned safety."""
    plugin_ids, id_errors = _receipt_plugin_ids(receipt)
    invalid = adapter.validate_uninstall_receipt(
        receipt,
        plugin_ids,
        expected_uninstall_plugin_ids(plugin_ids),
        identity_errors=id_errors,
    )
    if invalid is not None:
        return invalid
    rule_entry, rule_preflight = _receipt_owned_rule(adapter, receipt)
    if rule_preflight.state is ResultState.BLOCKED:
        return rule_preflight
    capabilities = adapter.remove_capabilities(receipt)

    before, error = adapter._list_installed()
    if error is not None:
        return combine_results(rule_preflight, capabilities, error)
    assert before is not None
    unowned = before - set(plugin_ids)

    failures = _remove_plugins(adapter, plugin_ids)

    after, list_error = adapter._list_installed()
    if list_error is not None:
        return combine_results(rule_preflight, capabilities, *failures, list_error)
    assert after is not None
    ownership = _uninstall_inventory_result(plugin_ids, unowned, after)
    if failures or ownership.state is ResultState.BLOCKED:
        return combine_results(rule_preflight, capabilities, *failures, ownership)

    rule = (
        adapter.restore_receipt_owned_file(rule_entry)
        if rule_entry is not None
        else HarnessResult("devin", ResultState.READY, (), {})
    )
    if rule.state is ResultState.BLOCKED:
        return combine_results(rule_preflight, capabilities, ownership, rule)

    command, error = adapter._execute((adapter.name, "plugins", "prune"))
    if error is not None:
        return combine_results(rule_preflight, rule, capabilities, error)
    assert command is not None
    if command.returncode != 0:
        failure = native_command_result(adapter.name, command, CapabilityTier.REQUIRED)
        return combine_results(rule_preflight, rule, capabilities, failure)

    final, final_error = adapter._list_installed()
    if final_error is not None:
        return combine_results(rule_preflight, rule, capabilities, final_error)
    assert final is not None
    return combine_results(
        rule_preflight,
        rule,
        capabilities,
        _uninstall_inventory_result(plugin_ids, unowned, final),
    )


def _receipt_owned_rule(
    adapter: DevinAdapter, receipt: HarnessReceipt
) -> tuple[OwnedEntry | None, HarnessResult]:
    entries = tuple(
        entry for entry in receipt.owned_entries if entry.kind == "owned-file"
    )
    if not entries:
        return None, HarnessResult("devin", ResultState.READY, (), {})
    if len(entries) == 1 and entries[0].identifier == "devin-global-rules":
        return entries[0], adapter.validate_receipt_owned_file(entries[0])
    return None, blocked("receipt lacks exact Devin global rule ownership")


def _remove_plugins(
    adapter: DevinAdapter, plugin_ids: Sequence[str]
) -> list[HarnessResult]:
    failures: list[HarnessResult] = []
    for plugin_id in plugin_ids:
        command, error = adapter._execute(
            (adapter.name, "plugins", "remove", plugin_id)
        )
        if error is not None:
            failures.append(error)
        elif command is not None and command.returncode != 0:
            failures.append(
                native_command_result(adapter.name, command, CapabilityTier.REQUIRED)
            )
    return failures


def blocked(error: str) -> HarnessResult:
    """Return a redacted Devin lifecycle blocker."""
    return HarnessResult(
        "devin", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )


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


def _uninstall_inventory_result(
    owned: Sequence[str], unowned: set[str], observed: set[str]
) -> HarnessResult:
    remaining = tuple(plugin_id for plugin_id in owned if plugin_id in observed)
    missing_unowned = tuple(sorted(unowned - observed))
    errors = tuple(
        f"receipt-owned plugin remains installed: {plugin_id}"
        for plugin_id in remaining
    ) + tuple(
        f"unowned plugin disappeared during uninstall: {plugin_id}"
        for plugin_id in missing_unowned
    )
    return HarnessResult(
        "devin",
        ResultState.BLOCKED if errors else ResultState.READY,
        remaining,
        {},
        errors=errors,
    )
