"""Receipt, snapshot, checksum, and reporting support for lifecycle services."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from manifest_agent import __version__
from manifest_agent.adapters.base import Detection, HarnessAdapter
from manifest_agent.models import (
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    ResultState,
)
from manifest_agent.process import redact_text
from manifest_agent.state import write_receipt_atomic

STATE_PRIORITY = {
    ResultState.READY: 0,
    ResultState.DEGRADED: 1,
    ResultState.DRIFTED: 2,
    ResultState.BLOCKED: 3,
}
NON_SUCCESS = {
    "blocked",
    "degraded",
    "drifted",
    "failed",
    "not-installed",
    "not_installed",
    "skipped",
    "unavailable",
    "unsupported",
}
_CREDENTIAL_KEY = re.compile(
    r"(?:^|[._-])(?:authorization|credential|password|private[_-]?key|secret|token|"
    r"api[_-]?key|access[_-]?key)(?:$|[._-])",
    re.I,
)


@dataclass(frozen=True)
class ServiceReport:
    """Stable, secret-free result returned by every lifecycle operation."""

    operation: str
    state: ResultState
    harnesses: dict[str, HarnessResult]
    notes: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "harnesses",
            {name: _safe_result(result) for name, result in self.harnesses.items()},
        )
        object.__setattr__(self, "notes", tuple(map(redact_text, self.notes)))
        object.__setattr__(self, "errors", tuple(map(redact_text, self.errors)))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible report."""
        harnesses = {}
        for name, result in self.harnesses.items():
            harnesses[name] = {
                "state": result.state.value,
                "installed_plugin_ids": list(result.installed_plugin_ids),
                "capabilities": dict(sorted(result.capabilities.items())),
                "errors": list(result.errors),
                "warnings": list(result.warnings),
            }
        return {
            "operation": self.operation,
            "state": self.state.value,
            "harnesses": harnesses,
            "notes": list(self.notes),
            "errors": list(self.errors),
        }


def report(operation, harnesses, notes=(), errors=()) -> ServiceReport:
    """Aggregate the strongest truthful result without exposing diagnostics."""
    state = ResultState.BLOCKED if errors else ResultState.READY
    if harnesses:
        state = max(
            (state, *(result.state for result in harnesses.values())),
            key=STATE_PRIORITY.__getitem__,
        )
    return ServiceReport(
        operation,
        state,
        dict(harnesses),
        tuple(redact_text(note) for note in notes),
        tuple(redact_text(error) for error in errors),
    )


def diagnostic(exception: Exception) -> str:
    """Redact an exception at the service boundary."""
    return redact_text(f"{type(exception).__name__}: {exception}")


def _safe_result(result: HarnessResult) -> HarnessResult:
    capabilities = {}
    for index, (key, value) in enumerate(result.capabilities.items()):
        safe_key = f"[REDACTED-{index}]" if _CREDENTIAL_KEY.search(key) else key
        capabilities[redact_text(safe_key)] = redact_text(value)
    return replace(
        result,
        installed_plugin_ids=tuple(map(redact_text, result.installed_plugin_ids)),
        capabilities=capabilities,
        errors=tuple(map(redact_text, result.errors)),
        warnings=tuple(map(redact_text, result.warnings)),
        owned_entries=(),
    )


def ordered(values, harness_order):
    """Return harness-keyed values in the public deterministic order."""
    unknown = set(values) - set(harness_order)
    if unknown:
        raise ValueError(f"unsupported harness keys: {', '.join(sorted(unknown))}")
    return {name: values[name] for name in harness_order if name in values}


def identity_errors(receipt, desired, checksums) -> tuple[str, ...]:
    """Compare durable immutable identity against the selected release."""
    errors = []
    comparisons = (
        (receipt.release_version, desired.release_version, "release version"),
        (receipt.source_commit, desired.source_commit, "source commit"),
        (receipt.archive_sha256, desired.archive_sha256, "release checksum"),
        (receipt.bundle_checksums, checksums, "bundle checksums"),
        (
            receipt.selected_optional,
            tuple(sorted(desired.selected_optional)),
            "optional capability selection",
        ),
    )
    for observed, expected, label in comparisons:
        if observed != expected:
            errors.append(f"{label} differs from the receipt")
    return tuple(errors)


def bundle_checksums(desired: DesiredState) -> dict[str, str]:
    """Digest each complete portable bundle using stable relative identities."""
    return {
        contract.name: _tree_checksum(desired.bundle_path(contract.name))
        for contract in desired.contracts
    }


def _tree_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_symlink():
            target = path.readlink().as_posix().encode()
            digest.update(b"l" + len(target).to_bytes(8, "big") + target)
            continue
        if path.is_dir():
            digest.update(b"d")
            continue
        digest.update(b"f")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def build_receipt(
    desired,
    results,
    detections,
    adapters,
    harness_order,
    previous=None,
) -> InstallationReceipt:
    """Create a truthful partial or complete receipt from effective results."""
    harnesses = dict(previous.harnesses) if previous is not None else {}
    for name, result in results.items():
        harnesses[name] = _harness_receipt(
            adapters.get(name),
            detections.get(name),
            result,
            harnesses.get(name),
        )
    return InstallationReceipt(
        1,
        __version__,
        desired.release_version,
        desired.source_commit,
        desired.source_dirty,
        desired.archive_sha256,
        bundle_checksums(desired),
        tuple(sorted(desired.selected_optional)),
        ordered(harnesses, harness_order),
        previous.migration_backup if previous is not None else None,
    )


def _harness_receipt(
    adapter: HarnessAdapter | None,
    detection: Detection | None,
    result: HarnessResult,
    previous: HarnessReceipt | None,
) -> HarnessReceipt:
    verified = result.state in {ResultState.READY, ResultState.DEGRADED}
    capabilities = dict(result.capabilities)
    errors = () if verified else result.errors or (f"{result.state.value} result",)
    if not verified:
        capabilities = {
            key: value if value.lower() in NON_SUCCESS else result.state.value.lower()
            for key, value in capabilities.items()
        }
    plugin_ids = result.installed_plugin_ids or (
        previous.plugin_ids if previous is not None else ()
    )
    owned_entries = tuple(
        dict.fromkeys(
            (
                *(previous.owned_entries if previous is not None else ()),
                *result.owned_entries,
            )
        )
    )
    native_version = (
        detection.version if detection is not None and detection.version else "unknown"
    )
    return HarnessReceipt(
        result.harness,
        getattr(adapter, "adapter_version", "unknown"),
        native_version,
        plugin_ids,
        owned_entries,
        capabilities,
        verified,
        tuple(redact_text(error) for error in errors),
    )


def snapshot_declared(selected, desired, adapters, snapshot_root):
    """Copy only existing files explicitly declared by selected adapters."""
    failures = {}
    for name in selected:
        declaration = getattr(adapters[name], "snapshot_paths", None)
        if declaration is None:
            continue
        try:
            for value in declaration(desired):
                source = Path(value)
                if not source.exists():
                    continue
                if not source.is_file():
                    raise ValueError("declared snapshot path must be a file")
                digest = hashlib.sha256(str(source).encode()).hexdigest()[:16]
                destination = snapshot_root / name / f"{digest}-{source.name}.bak"
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(source, destination)
        # constitution: exempt C-ERR -- adapter declarations are a trust boundary.
        except Exception as exception:
            failures[name] = HarnessResult(
                name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(diagnostic(exception),),
            )
    return failures


def persist_remaining(receipt_path, receipt, remaining, harness_order) -> None:
    """Retain failed/unselected ownership or remove the exhausted receipt."""
    if remaining:
        write_receipt_atomic(
            receipt_path,
            replace(receipt, harnesses=ordered(remaining, harness_order)),
        )
        return
    receipt_path.unlink(missing_ok=True)


__all__ = [
    "ServiceReport",
    "build_receipt",
    "bundle_checksums",
    "diagnostic",
    "identity_errors",
    "ordered",
    "persist_remaining",
    "report",
    "snapshot_declared",
]
