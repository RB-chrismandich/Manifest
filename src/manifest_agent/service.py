"""Convergent install, reconciliation, and receipt-owned removal services."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from manifest_agent import __version__
from manifest_agent.adapters.base import Detection, HarnessAdapter, combine_results
from manifest_agent.adapters.registry import AdapterRegistry
from manifest_agent.capabilities import resolve_capabilities
from manifest_agent.contracts import load_domain_contracts
from manifest_agent.models import (
    DesiredState,
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
from manifest_agent.state import installation_lock, read_receipt, write_receipt_atomic

HARNESS_ORDER = ("claude", "codex", "gemini", "cursor", "antigravity", "devin")


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

    def reconcile(self, apply: bool = False) -> ServiceReport:
        """Inspect desired state and optionally repair only drift or degradation."""
        try:
            receipt = read_receipt(self.receipt_path)
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report("reconcile", {}, errors=(diagnostic(exception),))
        if receipt is None:
            return report(
                "reconcile", {}, errors=("no installation receipt is available",)
            )
        desired, error = self._desired_state(receipt.release_version)
        if error is not None:
            return report("reconcile", {}, errors=(error,))
        assert desired is not None
        if not apply:
            return self._reconcile_locked(receipt, desired, apply=False)
        try:
            with self.lock_factory(self.receipt_path.parent / "install.lock"):
                return self._reconcile_locked(receipt, desired, apply=True)
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report("reconcile", {}, errors=(diagnostic(exception),))

    def uninstall(self) -> ServiceReport:
        """Remove only receipt-recorded ownership in reverse harness order."""
        try:
            receipt = read_receipt(self.receipt_path)
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report("uninstall", {}, errors=(diagnostic(exception),))
        if receipt is None:
            return report("uninstall", {}, notes=("nothing is installed",))
        results = {}
        notes = []
        remaining = dict(receipt.harnesses)
        try:
            with self.lock_factory(self.receipt_path.parent / "install.lock"):
                for name in reversed(_uninstall_selection(self, receipt)):
                    adapter = self.adapters.get(name)
                    owned = receipt.harnesses.get(name)
                    if adapter is None:
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
                persist_remaining(self.receipt_path, receipt, remaining, HARNESS_ORDER)
        # constitution: exempt C-ERR -- service boundary converts failures to BLOCKED.
        except Exception as exception:
            return report(
                "uninstall",
                ordered(results, HARNESS_ORDER),
                errors=(diagnostic(exception),),
            )
        return report("uninstall", ordered(results, HARNESS_ORDER), notes)

    def _reconcile_locked(
        self,
        receipt: InstallationReceipt,
        desired: DesiredState,
        *,
        apply: bool,
    ) -> ServiceReport:
        selected, detections, missing, notes = self._detect_requested()
        results = dict(missing)
        release_errors = identity_errors(receipt, desired, bundle_checksums(desired))
        for name in selected:
            adapter = self.adapters[name]
            inspected = _adapter_call(name, adapter.inspect, desired)
            drift_errors = _harness_drift_errors(receipt, name, adapter, release_errors)
            current = (
                combine_results(_drift_result(name, drift_errors), inspected)
                if drift_errors
                else inspected
            )
            if apply and current.state in {ResultState.DRIFTED, ResultState.DEGRADED}:
                installed = _adapter_call(name, adapter.install, desired)
                verified = _adapter_call(name, adapter.inspect, desired)
                current = combine_results(installed, verified)
            results[name] = current
        results = ordered(results, HARNESS_ORDER)
        if apply:
            updated = build_receipt(
                desired,
                results,
                detections,
                self.adapters,
                HARNESS_ORDER,
                previous=receipt,
            )
            write_receipt_atomic(self.receipt_path, updated)
        return report("reconcile", results, notes)

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


def _normalize_harnesses(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(value.lower() for value in values))
    if "all" in normalized and normalized != ("all",):
        raise ValueError("harness 'all' cannot be combined with named harnesses")
    unknown = set(normalized) - set(HARNESS_ORDER) - {"all"}
    if unknown:
        raise ValueError(f"unsupported harnesses: {', '.join(sorted(unknown))}")
    return tuple(name for name in HARNESS_ORDER if name in normalized) or normalized


__all__ = ["HARNESS_ORDER", "ManifestService", "ServiceReport"]
