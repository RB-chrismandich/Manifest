"""Convergent install, reconciliation, and receipt-owned removal services."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import replace
from pathlib import Path
from shlex import quote
from typing import Any

from manifest_agent import __version__
from manifest_agent.adapters.base import Detection, HarnessAdapter, combine_results
from manifest_agent.adapters.registry import AdapterRegistry
from manifest_agent.capabilities import resolve_capabilities
from manifest_agent.contracts import DOMAIN_BUNDLES, load_domain_contracts
from manifest_agent.migration import MigrationService
from manifest_agent.models import (
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    ResultState,
)
from manifest_agent.paths import xdg_paths
from manifest_agent.process import CommandRunner, redact_text
from manifest_agent.release import ResolvedRelease, resolve_release
from manifest_agent.service_state import (
    ServiceReport,
    build_receipt,
    bundle_checksums,
    diagnostic,
    identity_errors,
    ordered,
    persist_remaining,
    report,
    snapshot_declared,
)
from manifest_agent.state import (
    RetiredGraphifyTransaction,
    clear_retired_graphify_transaction,
    installation_lock,
    read_receipt,
    read_retired_graphify_transaction,
    receipt_digest,
    retired_graphify_transaction_path,
    write_receipt_atomic,
    write_retired_graphify_transaction_atomic,
)

HARNESS_ORDER = ("claude", "codex", "gemini", "cursor", "antigravity", "devin")
_RETIRED_BUNDLE = "manifest-graphify"
_RETIRED_EXECUTABLE = "graphify"


class ManifestService:
    """Coordinate native adapters around one immutable desired state."""

    def __init__(
        self,
        *,
        source: Path | None = None,
        release: str | None = None,
        harnesses: Sequence[str] = (),
        selected_optional: Sequence[str] = (),
        non_interactive: bool = False,
        adapters: Mapping[str, HarnessAdapter] | None = None,
        receipt_path: Path | None = None,
        snapshot_root: Path | None = None,
        release_resolver: Callable[[str | Path], ResolvedRelease] = resolve_release,
        contract_loader: Callable[[Path], tuple[Any, ...]] = load_domain_contracts,
        capability_planner: Callable[[Sequence[Any], Sequence[str]], Any] = (
            resolve_capabilities
        ),
        lock_factory: Callable[[Path | None], AbstractContextManager[Any]] = (
            installation_lock
        ),
        runner: CommandRunner | None = None,
    ) -> None:
        if source is not None and release is not None:
            raise ValueError("source and release are mutually exclusive")
        self.source = Path(source) if source is not None else None
        self.release = release
        self.harnesses = _normalize_harnesses(harnesses)
        self.selected_optional = tuple(dict.fromkeys(selected_optional))
        self.non_interactive = non_interactive
        self.receipt_path = receipt_path or xdg_paths().state / "installation.json"
        self.snapshot_root = snapshot_root or self.receipt_path.parent / "snapshots"
        self.release_resolver = release_resolver
        self.contract_loader = contract_loader
        self.capability_planner = capability_planner
        self.lock_factory = lock_factory
        self.runner = runner or CommandRunner()
        self.adapters = (
            dict(adapters)
            if adapters is not None
            else {name: AdapterRegistry.create(name) for name in HARNESS_ORDER}
        )
        unsupported = set(self.adapters) - set(HARNESS_ORDER)
        if unsupported:
            raise ValueError(
                f"unsupported adapter names: {', '.join(sorted(unsupported))}"
            )

    def install(self) -> ServiceReport:
        """Install and verify requested harnesses while preserving partial success."""
        desired, error = self._desired_state()
        if error is not None:
            return report("install", {}, errors=(error,))
        assert desired is not None
        selected, detections, missing, notes = self._detect_requested()
        results = dict(missing)
        try:
            with self.lock_factory(self.receipt_path.parent / "install.lock"):
                previous = read_receipt(self.receipt_path)
                if previous is not None:
                    previous, upgrade_error = self._upgrade_retired_graphify_receipt(
                        previous, desired
                    )
                    if upgrade_error is not None:
                        return report("install", {}, errors=(upgrade_error,))
                    assert previous is not None
                    conflicts = identity_errors(
                        previous, desired, bundle_checksums(desired)
                    )
                    if conflicts:
                        return report(
                            "install",
                            {},
                            errors=(
                                "existing receipt has incompatible release identity; "
                                "use deliberate migration: " + "; ".join(conflicts),
                            ),
                        )
                elif retired_graphify_transaction_path(self.receipt_path).exists():
                    # A journal without its bound receipt cannot prove safe recovery.
                    read_retired_graphify_transaction(
                        retired_graphify_transaction_path(self.receipt_path)
                    )
                    return report(
                        "install",
                        {},
                        errors=(
                            "retired Graphify transaction has no matching installation "
                            "receipt",
                        ),
                    )
                failures = snapshot_declared(
                    selected, desired, self.adapters, self.snapshot_root
                )
                for name in selected:
                    if name in failures:
                        results[name] = failures[name]
                        continue
                    adapter = self.adapters[name]
                    installed = _adapter_call(name, adapter.install, desired)
                    inspected = _adapter_call(name, adapter.inspect, desired)
                    results[name] = combine_results(installed, inspected)
                results = ordered(results, HARNESS_ORDER)
                receipt = build_receipt(
                    desired,
                    results,
                    detections,
                    self.adapters,
                    HARNESS_ORDER,
                    previous=previous,
                )
                write_receipt_atomic(self.receipt_path, receipt)
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report(
                "install",
                ordered(results, HARNESS_ORDER),
                notes,
                (diagnostic(exception),),
            )
        return report("install", results, notes)

    def _upgrade_retired_graphify_receipt(
        self, receipt: InstallationReceipt, desired: DesiredState
    ) -> tuple[InstallationReceipt | None, str | None]:
        """Durably replace a validated nine-bundle receipt with the current inventory."""
        checksums = bundle_checksums(desired)
        transaction_path = retired_graphify_transaction_path(self.receipt_path)
        transaction = read_retired_graphify_transaction(transaction_path)

        if transaction is not None:
            target_errors = identity_errors(
                transaction.target_receipt, desired, checksums
            )
            if target_errors:
                return None, (
                    "retired Graphify transaction target is incompatible with the "
                    "current release: " + "; ".join(target_errors)
                )
            if receipt == transaction.target_receipt:
                try:
                    clear_retired_graphify_transaction(transaction_path)
                # constitution: exempt C-ERR -- journal cleanup is a state boundary.
                except Exception as exception:
                    return None, diagnostic(exception)
                return receipt, None
            if receipt_digest(receipt) != transaction.legacy_receipt_digest:
                return None, (
                    "retired Graphify transaction does not match the current legacy "
                    "receipt"
                )
            if not _is_graphify_retirement_receipt(receipt, desired, checksums):
                return None, (
                    "retired Graphify transaction legacy receipt is incompatible with "
                    "the current release"
                )
            upgraded = transaction.target_receipt
        else:
            if not _is_graphify_retirement_receipt(receipt, desired, checksums):
                return receipt, None
            upgraded = replace(
                receipt,
                release_version=desired.release_version,
                source_commit=desired.source_commit,
                source_dirty=desired.source_dirty,
                archive_sha256=desired.archive_sha256,
                bundle_checksums=checksums,
                harnesses={
                    name: _without_retired_graphify(harness)
                    for name, harness in receipt.harnesses.items()
                },
            )
            if identity_errors(upgraded, desired, checksums):
                return (
                    None,
                    "retired receipt cannot be reconciled with the current release",
                )
            transaction = RetiredGraphifyTransaction(
                phase="prepared",
                legacy_receipt_digest=receipt_digest(receipt),
                target_receipt=upgraded,
            )
            try:
                write_retired_graphify_transaction_atomic(
                    transaction_path, transaction
                )
            # constitution: exempt C-ERR -- durable intent is a state boundary.
            except Exception as exception:
                return None, diagnostic(exception)

        if transaction.phase == "prepared" and _receipt_owns_retired_graphify(receipt):
            # read_receipt validated every ownership HMAC before the journal was created.
            try:
                command = self.runner.run(("uv", "tool", "uninstall", "graphifyy"))
            # constitution: exempt C-ERR -- native cleanup must block the upgrade.
            except Exception as exception:
                return None, diagnostic(exception)
            if command.returncode != 0:
                return None, redact_text(
                    "legacy Graphify cleanup failed: "
                    f"exit {command.returncode}: {command.stderr or command.stdout}"
                )

        if transaction.phase == "prepared":
            try:
                write_retired_graphify_transaction_atomic(
                    transaction_path,
                    replace(transaction, phase="cleanup-complete"),
                )
            # constitution: exempt C-ERR -- cleanup completion must be durable.
            except Exception as exception:
                return None, diagnostic(exception)
        try:
            write_receipt_atomic(self.receipt_path, upgraded)
        # constitution: exempt C-ERR -- atomic state persistence is a service boundary.
        except Exception as exception:
            return None, diagnostic(exception)
        try:
            clear_retired_graphify_transaction(transaction_path)
        # constitution: exempt C-ERR -- journal cleanup is a state boundary.
        except Exception as exception:
            return None, diagnostic(exception)
        return upgraded, None

    def migrate(self) -> ServiceReport:
        """Atomically hand bootstrap-owned writers to verified native plugins."""
        desired, error = self._desired_state()
        if error is not None:
            return report("migrate", {}, errors=(error,))
        assert desired is not None
        migration = MigrationService.from_manifest_service(self, paths=xdg_paths())
        result = migration.migrate(desired)
        if result.state is ResultState.BLOCKED:
            harnesses = " ".join(
                f"--harness {name}" for name in (self.harnesses or ("all",))
            )
            source = (
                f"--source {quote(str(self.source))}"
                if self.source is not None
                else f"--release {self.release or desired.release_version}"
            )
            optional = " ".join(
                f"--with {quote(capability)}" for capability in self.selected_optional
            )
            command = (
                "uvx --from manifest-agent manifest migrate "
                f"{source} {harnesses} {optional} --non-interactive"
            )
            return replace(result, notes=(*result.notes, f"resume with: {command}"))
        return result

    def reconcile(self, apply: bool = False) -> ServiceReport:
        """Inspect desired state and optionally repair only drift or degradation."""
        if apply:
            try:
                with self.lock_factory(self.receipt_path.parent / "install.lock"):
                    receipt = read_receipt(self.receipt_path)
                    return self._reconcile(receipt, apply=True)
            # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
            except Exception as exception:
                return report("reconcile", {}, errors=(diagnostic(exception),))
        try:
            receipt = read_receipt(self.receipt_path)
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report("reconcile", {}, errors=(diagnostic(exception),))
        return self._reconcile(receipt, apply=False)

    def _reconcile(
        self, receipt: InstallationReceipt | None, *, apply: bool
    ) -> ServiceReport:
        if receipt is None:
            return report(
                "reconcile", {}, errors=("no installation receipt is available",)
            )
        desired, error = self._desired_state(receipt.release_version)
        if error is not None:
            return report("reconcile", {}, errors=(error,))
        assert desired is not None
        return _reconcile_desired(self, receipt, desired, apply=apply)

    def uninstall(self) -> ServiceReport:
        """Remove only receipt-recorded ownership in reverse harness order."""
        results = {}
        notes = []
        try:
            with self.lock_factory(self.receipt_path.parent / "install.lock"):
                receipt = read_receipt(self.receipt_path)
                if receipt is None:
                    return report("uninstall", {}, notes=("nothing is installed",))
                remaining = dict(receipt.harnesses)
                for name in reversed(_uninstall_selection(self, receipt)):
                    adapter = self.adapters.get(name)
                    owned = receipt.harnesses.get(name)
                    if adapter is None:
                        results[name] = _missing_result(
                            name,
                            Detection(False, None, None, "harness adapter unavailable"),
                        )
                        continue
                    detection = _detect(name, adapter)
                    if not detection.present:
                        results[name] = _missing_result(name, detection)
                        continue
                    if owned is None:
                        notes.append(f"{name}: no recorded Manifest ownership")
                        continue
                    result = _adapter_call(name, adapter.uninstall, owned)
                    results[name] = result
                    if result.state is ResultState.READY:
                        remaining.pop(name, None)
                        _persist_progress(
                            self.receipt_path, receipt, remaining, HARNESS_ORDER
                        )
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report(
                "uninstall",
                ordered(results, HARNESS_ORDER),
                errors=(diagnostic(exception),),
            )
        return report("uninstall", ordered(results, HARNESS_ORDER), notes)

    def _desired_state(
        self, receipt_release: str | None = None
    ) -> tuple[DesiredState | None, str | None]:
        selector: str | Path = (
            self.source or self.release or receipt_release or __version__
        )
        try:
            resolved = self.release_resolver(selector)
            contracts = self.contract_loader(resolved.release_root / "plugins")
            self.capability_planner(contracts, self.selected_optional)
            return (
                DesiredState(
                    resolved.version,
                    resolved.source_commit,
                    resolved.source,
                    resolved.marketplace_source,
                    resolved.release_root,
                    resolved.repository_url,
                    resolved.source_dirty,
                    resolved.archive_sha256,
                    tuple(contracts),
                    frozenset(self.selected_optional),
                    self.harnesses,
                ),
                None,
            )
        # constitution: exempt C-ERR -- release/contracts are a trust boundary.
        except Exception as exception:
            return None, diagnostic(exception)

    def _detect_requested(self):
        explicit = bool(self.harnesses)
        candidates = (
            tuple(self.adapters)
            if not explicit or self.harnesses == ("all",)
            else self.harnesses
        )
        candidates = tuple(name for name in HARNESS_ORDER if name in candidates)
        selected, detections, missing, notes = [], {}, {}, []
        for name in candidates:
            detection = _detect(name, self.adapters[name])
            detections[name] = detection
            if detection.present:
                selected.append(name)
            elif explicit:
                missing[name] = _missing_result(name, detection)
            else:
                notes.append(f"{name}: {detection.reason or 'CLI not present'}")
        return tuple(selected), detections, missing, tuple(notes)


def _is_graphify_retirement_receipt(receipt, desired, checksums) -> bool:
    """Accept only a signed receipt whose sole bundle delta is retired Graphify."""
    legacy_bundles = set(DOMAIN_BUNDLES) | {_RETIRED_BUNDLE}
    if set(receipt.bundle_checksums) != legacy_bundles:
        return False
    if any(receipt.bundle_checksums[name] != checksums[name] for name in DOMAIN_BUNDLES):
        return False
    return receipt.selected_optional == tuple(sorted(desired.selected_optional))


def _without_retired_graphify(receipt: HarnessReceipt) -> HarnessReceipt:
    """Drop only retired bundle and capability facts after native cleanup succeeds."""
    retired_plugin_ids = {_RETIRED_BUNDLE, f"{_RETIRED_BUNDLE}@manifest"}
    retired_capabilities = {
        f"executable:{_RETIRED_EXECUTABLE}",
        f"{_RETIRED_BUNDLE}:executable:{_RETIRED_EXECUTABLE}",
    }
    return replace(
        receipt,
        plugin_ids=tuple(
            plugin_id
            for plugin_id in receipt.plugin_ids
            if plugin_id not in retired_plugin_ids
        ),
        owned_entries=tuple(
            entry
            for entry in receipt.owned_entries
            if not (
                entry.kind == "executable"
                and entry.identifier == _RETIRED_EXECUTABLE
            )
        ),
        capabilities={
            identity: state
            for identity, state in receipt.capabilities.items()
            if identity not in retired_capabilities
        },
    )


def _receipt_owns_retired_graphify(receipt: InstallationReceipt) -> bool:
    """Require receipt-proven executable ownership before native cleanup."""
    return any(
        entry.kind == "executable" and entry.identifier == _RETIRED_EXECUTABLE
        for harness in receipt.harnesses.values()
        for entry in harness.owned_entries
    )


def _detect(name: str, adapter: HarnessAdapter) -> Detection:
    try:
        return adapter.detect()
    # constitution: exempt C-ERR -- adapters are a native process boundary.
    except Exception as exception:
        return Detection(False, None, None, diagnostic(exception))


def _adapter_call(name: str, operation: Callable[..., Any], arg: Any) -> HarnessResult:
    try:
        result = operation(arg)
        if not isinstance(result, HarnessResult) or result.harness != name:
            raise TypeError("adapter returned an invalid harness result")
        return result
    # constitution: exempt C-ERR -- adapters are a native process boundary.
    except Exception as exception:
        return HarnessResult(
            name, ResultState.BLOCKED, (), {}, errors=(diagnostic(exception),)
        )


def _reconcile_desired(service, receipt, desired, *, apply):
    selected, detections, missing, notes = _detect_reconcile(service, receipt)
    results = dict(missing)
    release_errors = identity_errors(receipt, desired, bundle_checksums(desired))
    owned_harnesses = set(receipt.harnesses)
    scoped_owned = (set(selected) | set(missing)) & owned_harnesses
    scope_error = _identity_scope_error(
        apply, release_errors, scoped_owned, owned_harnesses
    )
    if scope_error is not None:
        return report(
            "reconcile",
            results,
            notes,
            (scope_error,),
        )
    mutated_owned = set()
    for name in selected:
        adapter = service.adapters[name]
        inspected = _adapter_call(name, adapter.inspect, desired)
        drift_errors = _harness_drift_errors(receipt, name, adapter, release_errors)
        current = (
            combine_results(_drift_result(name, drift_errors), inspected)
            if drift_errors
            else inspected
        )
        if (
            apply
            and name in receipt.harnesses
            and current.state in {ResultState.DRIFTED, ResultState.DEGRADED}
        ):
            installed = _adapter_call(name, adapter.install, desired)
            mutated_owned.add(name)
            verified = _adapter_call(name, adapter.inspect, desired)
            current = combine_results(installed, verified)
        results[name] = current
    results = ordered(results, HARNESS_ORDER)
    persist_error = _persist_reconcile(
        service,
        receipt,
        desired,
        results,
        detections,
        release_errors,
        owned_harnesses,
        mutated_owned,
    )
    if persist_error is not None:
        return report("reconcile", results, notes, (persist_error,))
    return report("reconcile", results, notes)


def _identity_scope_error(apply, release_errors, scoped_owned, owned_harnesses):
    if apply and release_errors and scoped_owned and scoped_owned != owned_harnesses:
        return (
            "release identity change requires a full reconcile or migration; "
            "partial apply would create mixed receipt identity"
        )
    return None


def _persist_reconcile(
    service,
    receipt,
    desired,
    results,
    detections,
    release_errors,
    owned_harnesses,
    mutated_owned,
):
    if not mutated_owned:
        return None
    if release_errors and not all(
        name in results
        and results[name].state in {ResultState.READY, ResultState.DEGRADED}
        for name in owned_harnesses
    ):
        return "release identity remains unchanged until every owned harness converges"
    owned_results = {
        name: result for name, result in results.items() if name in receipt.harnesses
    }
    updated = build_receipt(
        desired,
        owned_results,
        detections,
        service.adapters,
        HARNESS_ORDER,
        previous=receipt,
    )
    write_receipt_atomic(service.receipt_path, updated)
    return None


def _detect_reconcile(service, receipt):
    if not service.harnesses:
        candidates = tuple(receipt.harnesses)
    elif service.harnesses == ("all",):
        candidates = tuple(service.adapters)
    else:
        candidates = service.harnesses
    candidates = tuple(name for name in HARNESS_ORDER if name in candidates)
    selected, detections, missing = [], {}, {}
    for name in candidates:
        adapter = service.adapters.get(name)
        detection = (
            Detection(False, None, None, "harness adapter unavailable")
            if adapter is None
            else _detect(name, adapter)
        )
        detections[name] = detection
        if detection.present:
            selected.append(name)
        else:
            missing[name] = _missing_result(name, detection)
    return tuple(selected), detections, missing, ()


def _missing_result(name: str, detection: Detection) -> HarnessResult:
    return HarnessResult(
        name,
        ResultState.BLOCKED,
        (),
        {"harness.cli": "unavailable"},
        errors=(redact_text(detection.reason or f"{name} CLI not present"),),
    )


def _drift_result(name: str, errors: Sequence[str]) -> HarnessResult:
    return HarnessResult(
        name,
        ResultState.DRIFTED,
        (),
        {"installation.identity": "drifted"},
        errors=tuple(errors),
    )


def _harness_drift_errors(receipt, name, adapter, release_errors):
    errors = list(release_errors)
    prior = receipt.harnesses.get(name)
    if prior is None:
        errors.append("harness is absent from the installation receipt")
    elif prior.adapter_version != getattr(adapter, "adapter_version", "unknown"):
        errors.append("adapter version differs from the receipt")
    elif not prior.verified:
        errors.append("receipt records an unverified harness")
    return errors


def _uninstall_selection(service, receipt) -> tuple[str, ...]:
    if not service.harnesses:
        names = receipt.harnesses
    elif service.harnesses == ("all",):
        names = service.adapters
    else:
        names = service.harnesses
    return tuple(name for name in HARNESS_ORDER if name in names)


def _persist_progress(receipt_path, receipt, remaining, harness_order) -> None:
    error = None
    for _attempt in range(2):
        try:
            persist_remaining(receipt_path, receipt, remaining, harness_order)
            return
        # constitution: exempt C-ERR -- retry one transient durable-state failure.
        except Exception as exception:
            error = exception
    assert error is not None
    raise error


def _normalize_harnesses(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(value.lower() for value in values))
    if "all" in normalized and normalized != ("all",):
        raise ValueError("harness 'all' cannot be combined with named harnesses")
    unknown = set(normalized) - set(HARNESS_ORDER) - {"all"}
    if unknown:
        raise ValueError(f"unsupported harnesses: {', '.join(sorted(unknown))}")
    return tuple(name for name in HARNESS_ORDER if name in normalized) or normalized


__all__ = ["HARNESS_ORDER", "ManifestService", "ServiceReport"]
