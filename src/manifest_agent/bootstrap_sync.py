# constitution: exempt C-SIZE -- the signed reconciliation saga is one auditable transaction.
"""Receipt-aware bootstrap convergence with a durable mutation saga."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from manifest_agent.adapters.base import combine_results
from manifest_agent.adapters.codex import CodexAdapter, _desired_target_identity
from manifest_agent.adapters.convergence import has_undeclared_degradation
from manifest_agent.codex_config import (
    PluginEnabledChange,
    apply_plugin_enabled,
    content_sha256,
    prepare_plugin_enabled,
    rollback_plugin_enabled,
)
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackup,
    plugin_tree_sha256,
    remove_plugin_backup,
    restore_plugin_backup,
)
from manifest_agent.codex_skill_cutover import (
    apply_codex_skill_cutover,
    commit_codex_skill_cutover,
    inspect_codex_skill_source,
    prepare_codex_skill_cutover,
    restore_codex_skills,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    AdapterMutationHandle,
    AdapterPluginState,
    HarnessReceipt,
    HarnessResult,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import (
    bootstrap_journal_errors,
    bootstrap_journal_proof,
    ensure_bootstrap_journal_authority,
)
from manifest_agent.service_state import (
    build_receipt,
    bundle_checksums,
    diagnostic,
    identity_errors,
    report,
)
from manifest_agent.state import (
    read_receipt,
    receipt_digest,
    receipt_for_persistence,
    write_receipt_atomic,
)

NO_PRIOR_RECEIPT_V1 = "NO_PRIOR_RECEIPT_V1"


@dataclass(frozen=True)
class RepairCheckpoint:
    phase: str
    backup: dict[str, Any]


@dataclass(frozen=True)
class HarnessMutationCheckpoint:
    harness: str
    phase: str
    handle: dict[str, Any]


@dataclass(frozen=True)
class ReconciliationSaga:
    phase: str
    harness: str
    repairs: tuple[RepairCheckpoint, ...] = ()
    plugin_change: dict[str, Any] | None = None
    cutover_entry: dict[str, Any] | None = None
    harness_mutations: tuple[HarnessMutationCheckpoint, ...] = ()
    prior_receipt_digest: str = NO_PRIOR_RECEIPT_V1
    target_identity: str = ""
    target_receipt_digest: str = ""


def _journal_path(receipt_path: Path) -> Path:
    return receipt_path.with_name(f".{receipt_path.name}.bootstrap-sync.json")


def _write_journal(path: Path, saga: ReconciliationSaga) -> None:
    from manifest_agent.state import _write_private_json_atomic

    key_path = path.parent / "ownership.key"
    if not key_path.exists() and not path.exists():
        ensure_bootstrap_journal_authority(
            key_path, receipt_exists=False, journal_exists=False
        )
    unsigned = {"schema_version": 1, **asdict(saga)}
    proof = bootstrap_journal_proof(unsigned, key_path=key_path)
    _write_private_json_atomic(path, {**unsigned, "ownership_proof": proof})


# constitution: exempt C-SIZE -- validation covers the complete signed journal schema atomically.
def _read_journal(
    path: Path,
    *,
    expected_prior_receipt_digest: str | None = None,
    expected_target_identity: str | None = None,
) -> ReconciliationSaga | None:
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError
        proof = document.pop("ownership_proof", None)
        authority_errors = bootstrap_journal_errors(
            document, proof, key_path=path.parent / "ownership.key"
        )
        if authority_errors:
            raise ValueError(authority_errors[0])
        repairs = document.get("repairs", [])
        if not isinstance(repairs, list):
            raise ValueError
        decoded_repairs: list[RepairCheckpoint] = []
        for item in repairs:
            if (
                not isinstance(item, dict)
                or item.get("phase") not in {"captured", "removed", "restored", "added"}
                or not isinstance(item.get("backup"), dict)
            ):
                raise ValueError
            CodexPluginBackup.from_dict(item["backup"])
            decoded_repairs.append(RepairCheckpoint(item["phase"], item["backup"]))
        plugin_change = document.get("plugin_change")
        cutover_entry = document.get("cutover_entry")
        harness_mutations = document.get("harness_mutations", [])
        if plugin_change is not None and not isinstance(plugin_change, dict):
            raise ValueError
        if cutover_entry is not None and not isinstance(cutover_entry, dict):
            raise ValueError
        if not isinstance(harness_mutations, list):
            raise ValueError
        decoded_mutations: list[HarnessMutationCheckpoint] = []
        for item in harness_mutations:
            if (
                not isinstance(item, dict)
                or set(item) != {"harness", "phase", "handle"}
                or not isinstance(item["harness"], str)
                or item["phase"]
                not in {
                    "prepared",
                    "applying",
                    "uncertain",
                    "applied",
                    "verified",
                    "rolled-back",
                    "tombstoned",
                }
                or not isinstance(item["handle"], dict)
            ):
                raise ValueError
            _deserialize_handle(item["handle"])
            decoded_mutations.append(HarnessMutationCheckpoint(**item))
        phase = document.get("phase")
        harness = document.get("harness")
        prior_receipt_digest = document.get("prior_receipt_digest")
        target_identity = document.get("target_identity")
        target_receipt_digest = document.get("target_receipt_digest", "")
        if (
            not isinstance(phase, str)
            or harness != "codex"
            or not isinstance(prior_receipt_digest, str)
            or not prior_receipt_digest
            or not isinstance(target_identity, str)
            or len(target_identity) != 64
            or not isinstance(target_receipt_digest, str)
            or (target_receipt_digest and len(target_receipt_digest) != 64)
            or (
                phase in {"receipt-prepared", "committed"}
                and len(target_receipt_digest) != 64
            )
        ):
            raise ValueError
        if (
            expected_prior_receipt_digest is not None
            and prior_receipt_digest != expected_prior_receipt_digest
        ):
            raise ValueError("journal prior receipt binding does not match")
        if (
            expected_target_identity is not None
            and target_identity != expected_target_identity
        ):
            raise ValueError("journal target identity does not match")
        return ReconciliationSaga(
            phase,
            harness,
            tuple(decoded_repairs),
            plugin_change,
            cutover_entry,
            tuple(decoded_mutations),
            prior_receipt_digest,
            target_identity,
            target_receipt_digest,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeError("bootstrap reconciliation journal is invalid") from error


def _serialize_change(change: PluginEnabledChange) -> dict[str, Any]:
    return asdict(change)


def _deserialize_change(value: Mapping[str, Any]) -> PluginEnabledChange:
    try:
        change = PluginEnabledChange(
            value["plugin_id"],
            value["previous"],
            value["current"],
            value["before_sha256"],
            value["written_sha256"],
            value["table_existed"],
            value["separator_added"],
        )
    except (KeyError, TypeError) as error:
        raise RuntimeError("bootstrap plugin change journal is invalid") from error
    if (
        change.plugin_id != "i-have-adhd@i-have-adhd"
        or change.previous not in {True, False, None}
        or not isinstance(change.current, bool)
        or not isinstance(change.before_sha256, str)
        or not isinstance(change.written_sha256, str)
        or not isinstance(change.table_existed, bool)
        or not isinstance(change.separator_added, bool)
        or (not change.table_existed and change.previous is not None)
        or (change.table_existed and change.separator_added)
    ):
        raise RuntimeError("bootstrap plugin change journal is invalid")
    return change


def _serialize_owned(entry: OwnedEntry) -> dict[str, Any]:
    return asdict(entry)


def _deserialize_owned(value: Mapping[str, Any]) -> OwnedEntry:
    try:
        entry = OwnedEntry(
            value["kind"],
            value["identifier"],
            value["ownership_marker"],
            value.get("target_path"),
            value.get("previous_checksum"),
        )
    except (KeyError, TypeError) as error:
        raise RuntimeError("bootstrap cutover journal is invalid") from error
    if entry.kind != "codex-skill-source" or entry.identifier != "codex-shared-skills":
        raise RuntimeError("bootstrap cutover journal is invalid")
    return entry


def _serialize_handle(handle: AdapterMutationHandle) -> dict[str, Any]:
    return asdict(handle)


# constitution: exempt C-SIZE -- compatibility validation covers one complete durable handle.
def _deserialize_handle(value: Mapping[str, Any]) -> AdapterMutationHandle:
    try:
        handle = AdapterMutationHandle(
            value["schema_version"],
            value["harness"],
            value["adapter_version"],
            value["target_identity"],
            tuple(AdapterPluginState(**item) for item in value["prior_inventory"]),
            tuple(AdapterPluginState(**item) for item in value["target_inventory"]),
            AdapterMarketplaceState(**value["prior_marketplace"])
            if value.get("prior_marketplace") is not None
            else None,
            AdapterMarketplaceState(**value["target_marketplace"])
            if value.get("target_marketplace") is not None
            else None,
            value.get("prior_cas"),
            value.get("target_cas"),
            value.get("prior_capabilities"),
            value.get("target_capabilities"),
            tuple(value.get("prior_owned_files", ())),
            tuple(value.get("target_owned_files", ())),
        )
    except (KeyError, TypeError) as error:
        raise RuntimeError("adapter reconciliation handle is invalid") from error
    if (
        set(value)
        != {
            "schema_version",
            "harness",
            "adapter_version",
            "target_identity",
            "prior_inventory",
            "target_inventory",
            "prior_marketplace",
            "target_marketplace",
            "prior_cas",
            "target_cas",
            "prior_capabilities",
            "target_capabilities",
            "prior_owned_files",
            "target_owned_files",
        }
        or handle.schema_version not in {1, 2}
        or not handle.harness
        or not handle.adapter_version
        or len(handle.target_identity) != 64
        or (handle.prior_cas is not None and len(handle.prior_cas) != 64)
        or (handle.target_cas is not None and len(handle.target_cas) != 64)
        or not isinstance(handle.prior_capabilities, (dict, type(None)))
        or not isinstance(handle.target_capabilities, (dict, type(None)))
        or any(not isinstance(item, dict) for item in handle.prior_owned_files)
        or any(not isinstance(item, dict) for item in handle.target_owned_files)
        or any(
            not item.identifier
            or not item.version
            or (item.installed_sha256 is not None and len(item.installed_sha256) != 64)
            or item.retirement_phase
            not in {None, "backed-up", "removal-prepared", "removed"}
            for item in (*handle.prior_inventory, *handle.target_inventory)
        )
    ):
        raise RuntimeError("adapter reconciliation handle is invalid")
    return handle


def _checkpoint_repair(
    journal: Path,
    saga: ReconciliationSaga,
    backup: CodexPluginBackup,
    phase: str,
) -> ReconciliationSaga:
    repairs = [
        item
        for item in saga.repairs
        if item.backup.get("plugin_id") != backup.plugin_id
    ]
    repairs.append(RepairCheckpoint(phase, backup.to_dict()))
    updated = replace(saga, phase="plugin-repair", repairs=tuple(repairs))
    _write_journal(journal, updated)
    return updated


# constitution: exempt C-SIZE -- recovery replays the ordered durable saga without hidden transitions.
def _recover_unfinished(
    journal: Path,
    saga: ReconciliationSaga,
    config_path: Path,
    *,
    observed_receipt_digest: str | None = None,
) -> ReconciliationSaga | None:
    if saga.phase == "committed":
        if (
            saga.target_receipt_digest
            and observed_receipt_digest != saga.target_receipt_digest
        ):
            raise RuntimeError(
                "committed reconciliation cleanup does not match the target receipt"
            )
        if saga.cutover_entry is not None:
            commit_codex_skill_cutover(_deserialize_owned(saga.cutover_entry))
        for item in saga.repairs:
            remove_plugin_backup(CodexPluginBackup.from_dict(item.backup))
        for mutation in saga.harness_mutations:
            for plugin in _deserialize_handle(mutation.handle).prior_inventory:
                if plugin.rollback_data is not None:
                    remove_plugin_backup(
                        CodexPluginBackup.from_dict(plugin.rollback_data)
                    )
        journal.unlink(missing_ok=True)
        return None
    if saga.cutover_entry is not None:
        entry = _deserialize_owned(saga.cutover_entry)
        try:
            raw_prior_target = json.loads(entry.previous_checksum or "")["prior_target"]
            prior_target = Path(raw_prior_target)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise RuntimeError(
                "bootstrap cutover recovery metadata is invalid"
            ) from error
        entry_path = Path(entry.target_path)
        expected_target = (
            prior_target
            if prior_target.is_absolute()
            else entry_path.parent / prior_target
        )
        state = inspect_codex_skill_source(entry_path.parents[1], expected_target)
        if state.kind == "system-only":
            restore_codex_skills(entry)
        elif state.kind != "legacy-link" or state.target != raw_prior_target:
            raise RuntimeError("bootstrap cutover recovery is ambiguous")
    if saga.plugin_change is not None:
        change = _deserialize_change(saga.plugin_change)
        current = config_path.read_bytes() if config_path.exists() else b""
        current_hash = content_sha256(current)
        if current_hash != change.before_sha256:
            rollback_plugin_enabled(config_path, change)
    recovered: list[RepairCheckpoint] = []
    for item in saga.repairs:
        backup = CodexPluginBackup.from_dict(item.backup)
        phase = item.phase
        installed_path = Path(backup.installed_path)
        if phase in {"captured", "removed"}:
            if not installed_path.exists():
                restore_plugin_backup(backup)
                phase = "restored"
            elif plugin_tree_sha256(installed_path) == backup.installed_sha256:
                phase = "restored"
            else:
                raise RuntimeError(
                    "bootstrap plugin repair recovery is ambiguous; installed target changed"
                )
        recovered.append(RepairCheckpoint(phase, item.backup))
    updated = ReconciliationSaga(
        "prepared",
        "codex",
        tuple(recovered),
        harness_mutations=saga.harness_mutations,
        prior_receipt_digest=saga.prior_receipt_digest,
        target_identity=saga.target_identity,
        target_receipt_digest=saga.target_receipt_digest,
    )
    _write_journal(journal, updated)
    if updated.harness_mutations and all(
        item.phase == "tombstoned" for item in updated.harness_mutations
    ):
        journal.unlink(missing_ok=True)
        for item in updated.repairs:
            remove_plugin_backup(CodexPluginBackup.from_dict(item.backup))
        for mutation in updated.harness_mutations:
            for plugin in _deserialize_handle(mutation.handle).prior_inventory:
                if plugin.rollback_data is not None:
                    remove_plugin_backup(
                        CodexPluginBackup.from_dict(plugin.rollback_data)
                    )
        return None
    return updated


def _blocked(message: str) -> HarnessResult:
    return HarnessResult("codex", ResultState.BLOCKED, (), {}, errors=(message,))


def _target_identity(desired) -> str:
    payload = json.dumps(
        {
            "release_version": desired.release_version,
            "source_commit": desired.source_commit,
            "archive_sha256": desired.archive_sha256,
            "bundle_checksums": bundle_checksums(desired),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


# constitution: exempt C-SIZE -- prepared participants converge in one fail-closed ordered pass.
def _converge_other_owned_harnesses(
    service,
    previous,
    desired,
    prior_desired,
    detections,
    checkpoint=None,
    prepared=(),
) -> tuple[dict[str, HarnessResult], str | None]:
    if previous is None or not identity_errors(
        previous, desired, bundle_checksums(desired)
    ):
        return {}, None
    names = tuple(name for name in previous.harnesses if name != "codex")
    unavailable: list[str] = []
    for name in names:
        adapter = service.adapters.get(name)
        if adapter is None:
            unavailable.append(name)
            continue
        try:
            detection = adapter.detect()
        except Exception as error:
            unavailable.append(f"{name} ({diagnostic(error)})")
            continue
        detections[name] = detection
        if not detection.present:
            unavailable.append(name)
    if unavailable:
        return {}, (
            "release identity change requires every receipt-owned harness; "
            "unavailable: " + ", ".join(unavailable)
        )
    results: dict[str, HarnessResult] = {}
    prepared_by_name = {item.harness: item for item in prepared}
    for name in names:
        adapter = service.adapters[name]
        mutation = prepared_by_name.get(name)
        if mutation is None:
            return results, f"missing prepared adapter mutation for {name}"
        handle = _deserialize_handle(mutation.handle)
        try:
            inspected = adapter.verify_reconcile(handle, desired)
            if inspected.state in {ResultState.READY, ResultState.DEGRADED}:
                result = inspected
            else:
                if checkpoint is not None:
                    checkpoint(name, "applying")
                installed = adapter.apply_reconcile(handle, desired)
                if checkpoint is not None:
                    checkpoint(name, "applied")
                inspected = adapter.verify_reconcile(handle, desired)
                result = combine_results(installed, inspected)
        except Exception as error:
            if checkpoint is not None:
                checkpoint(name, "uncertain")
            result = HarnessResult(
                name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(diagnostic(error),),
            )
        results[name] = result
        if result.state not in {ResultState.READY, ResultState.DEGRADED}:
            return results, (
                "release identity remains unchanged until every owned harness "
                f"converges; {name} is {result.state.value}"
            )
        if checkpoint is not None and name in prepared_by_name:
            checkpoint(name, "verified")
    return results, None


class _BootstrapAbort(RuntimeError):
    def __init__(self, message: str, results: Mapping[str, HarnessResult]) -> None:
        super().__init__(message)
        self.results = dict(results)


# constitution: exempt C-SIZE -- reverse-order compensation must remain visibly atomic.
def _compensate_harness_mutations(
    service,
    journal: Path,
    saga: ReconciliationSaga,
    prior_desired,
    desired,
) -> tuple[ReconciliationSaga, tuple[str, ...]]:
    """Classify and compensate every durable uncommitted participant."""
    errors: list[str] = []
    current = saga
    for item in reversed(saga.harness_mutations):
        if item.phase == "tombstoned":
            continue
        adapter = service.adapters.get(item.harness)
        if adapter is None:
            errors.append(f"{item.harness}: adapter unavailable")
            continue
        handle = _deserialize_handle(item.handle)
        try:
            observed = adapter.classify_reconcile_state(handle, desired)
        except Exception as error:
            mutations = tuple(
                replace(checkpoint, phase="uncertain")
                if checkpoint.harness == item.harness
                else checkpoint
                for checkpoint in current.harness_mutations
            )
            current = replace(
                current, phase="compensation-blocked", harness_mutations=mutations
            )
            _write_journal(journal, current)
            errors.append(
                f"{item.harness}: state classification failed: {diagnostic(error)}"
            )
            continue
        if observed == "other":
            mutations = tuple(
                replace(checkpoint, phase="uncertain")
                if checkpoint.harness == item.harness
                else checkpoint
                for checkpoint in current.harness_mutations
            )
            current = replace(
                current, phase="compensation-blocked", harness_mutations=mutations
            )
            _write_journal(journal, current)
            errors.append(
                f"{item.harness}: native state is neither exact prior nor target"
            )
            continue
        if observed == "target":
            try:
                rolled_back = adapter.rollback_reconcile(handle, prior_desired)
            except Exception as error:
                errors.append(f"{item.harness}: {diagnostic(error)}")
                continue
            if rolled_back.state not in {ResultState.READY, ResultState.DEGRADED}:
                errors.append(f"{item.harness}: {rolled_back.state.value}")
                continue
            try:
                if adapter.classify_reconcile_state(handle, desired) != "prior":
                    errors.append(
                        f"{item.harness}: compensation did not restore the exact prior"
                    )
                    continue
            except Exception as error:
                errors.append(
                    f"{item.harness}: compensation verification failed: {diagnostic(error)}"
                )
                continue
        mutations = tuple(
            replace(checkpoint, phase="tombstoned")
            if checkpoint.harness == item.harness
            else checkpoint
            for checkpoint in current.harness_mutations
        )
        current = replace(current, phase="compensating", harness_mutations=mutations)
        _write_journal(journal, current)
    return current, tuple(errors)


def _cleanup_saga_backups(saga: ReconciliationSaga) -> None:
    for item in saga.repairs:
        remove_plugin_backup(CodexPluginBackup.from_dict(item.backup))
    for mutation in saga.harness_mutations:
        for plugin in _deserialize_handle(mutation.handle).prior_inventory:
            if plugin.rollback_data is not None:
                remove_plugin_backup(CodexPluginBackup.from_dict(plugin.rollback_data))


def _retire_compensated_transaction(
    service, journal: Path, saga: ReconciliationSaga
) -> None:
    if not saga.harness_mutations or any(
        item.phase != "tombstoned" for item in saga.harness_mutations
    ):
        raise RuntimeError("reconciliation transaction is not fully tombstoned")
    receipt = read_receipt(service.receipt_path)
    observed_digest = (
        receipt_digest(receipt) if receipt is not None else NO_PRIOR_RECEIPT_V1
    )
    if observed_digest != saga.prior_receipt_digest:
        raise RuntimeError(
            "compensation did not preserve the authoritative prior receipt"
        )
    retired = replace(saga, phase="retired")
    _write_journal(journal, retired)
    _cleanup_saga_backups(retired)
    journal.unlink(missing_ok=True)


# constitution: exempt C-SIZE -- this class owns one durable reconciliation state machine.
class BootstrapSyncService:
    """Converge one enabled native harness before committing ownership."""

    def __init__(self, service) -> None:
        self.service = service

    # constitution: exempt C-SIZE -- lock, journal, native state, and receipt commit share rollback scope.
    def run(self, desired=None):
        if desired is None:
            desired, error = self.service._desired_state()
            if error is not None:
                return report("bootstrap-sync", {}, errors=(error,))
        assert desired is not None
        selected, detections, missing, notes = self.service._detect_requested()
        if missing:
            return report("bootstrap-sync", missing, notes)
        if "codex" not in selected:
            return report("bootstrap-sync", {}, notes)
        adapter = self.service.adapters["codex"]
        durable_codex = isinstance(adapter, CodexAdapter) and hasattr(adapter, "runner")
        journal = _journal_path(self.service.receipt_path)
        home = Path(os.environ.get("HOME", str(Path.home())))
        manifest_skills = Path(
            os.environ.get("MANIFEST_SKILLS_DIR", str(home / ".manifest" / "skills"))
        )
        config_path = Path(
            os.environ.get("CODEX_CONFIG_PATH", str(home / ".codex" / "config.toml"))
        )
        change: PluginEnabledChange | None = None
        cutover: OwnedEntry | None = None
        receipt_committed = False
        rollback_allowed = True
        saga: ReconciliationSaga | None = None
        prior_desired = desired
        synchronized: dict[str, HarnessResult] = {}
        try:
            with self.service.lock_factory(
                self.service.receipt_path.parent / "install.lock"
            ):
                key_path = self.service.receipt_path.parent / "ownership.key"
                ensure_bootstrap_journal_authority(
                    key_path,
                    receipt_exists=self.service.receipt_path.exists(),
                    journal_exists=journal.exists(),
                )
                previous = read_receipt(self.service.receipt_path)
                prior_digest = (
                    receipt_digest(previous)
                    if previous is not None
                    else NO_PRIOR_RECEIPT_V1
                )
                desired_identity = _target_identity(desired)
                saga = _read_journal(journal)
                recovered_transaction = saga is not None
                if saga is not None:
                    if saga.phase == "receipt-prepared" and (
                        saga.target_receipt_digest == prior_digest
                    ):
                        saga = replace(saga, phase="committed")
                        _write_journal(journal, saga)
                    elif saga.phase == "committed":
                        if saga.target_receipt_digest != prior_digest:
                            raise RuntimeError(
                                "bootstrap committed journal target receipt does not match"
                            )
                    elif saga.prior_receipt_digest != prior_digest:
                        raise RuntimeError(
                            "bootstrap reconciliation journal receipt/target binding does not match"
                        )
                if saga is None:
                    saga = ReconciliationSaga(
                        "prepared",
                        "codex",
                        prior_receipt_digest=prior_digest,
                        target_identity=desired_identity,
                    )
                    _write_journal(journal, saga)
                else:
                    saga = _recover_unfinished(
                        journal,
                        saga,
                        config_path,
                        observed_receipt_digest=prior_digest,
                    )
                    if saga is None:
                        saga = ReconciliationSaga(
                            "prepared",
                            "codex",
                            prior_receipt_digest=prior_digest,
                            target_identity=desired_identity,
                        )
                    _write_journal(journal, saga)

                def harness_checkpoint(name: str, phase: str) -> None:
                    nonlocal saga
                    mutations = [
                        replace(item, phase=phase) if item.harness == name else item
                        for item in saga.harness_mutations
                    ]
                    saga = replace(
                        saga,
                        phase="harness-convergence",
                        harness_mutations=tuple(mutations),
                    )
                    _write_journal(journal, saga)

                def codex_retirement_checkpoint(handle: AdapterMutationHandle) -> None:
                    nonlocal saga, codex_checkpoint
                    serialized = _serialize_handle(handle)
                    rollback_eligible = any(
                        item.retirement_phase in {"removal-prepared", "removed"}
                        for item in handle.prior_inventory
                    )
                    phase = "applied" if rollback_eligible else "prepared"
                    mutations = tuple(
                        replace(item, phase=phase, handle=serialized)
                        if item.harness == "codex"
                        else item
                        for item in saga.harness_mutations
                    )
                    codex_checkpoint = HarnessMutationCheckpoint(
                        "codex", phase, serialized
                    )
                    saga = replace(
                        saga,
                        phase="codex-retirement",
                        harness_mutations=mutations,
                    )
                    _write_journal(journal, saga)

                identity_changed = previous is not None and bool(
                    identity_errors(previous, desired, bundle_checksums(desired))
                )
                if identity_changed:
                    prior_desired, prior_error = self.service._desired_state(
                        previous.release_version, exact_release=True
                    )
                    if prior_error is not None or prior_desired is None:
                        raise RuntimeError(
                            "prior release is unavailable for cross-harness compensation"
                        )
                    if recovered_transaction and saga.harness_mutations:
                        saga, recovery_errors = _compensate_harness_mutations(
                            self.service,
                            journal,
                            saga,
                            prior_desired,
                            desired,
                        )
                        if recovery_errors:
                            raise RuntimeError(
                                "unfinished reconciliation recovery is BLOCKED: "
                                + "; ".join(recovery_errors)
                            )
                        _retire_compensated_transaction(self.service, journal, saga)
                        saga = ReconciliationSaga(
                            "prepared",
                            "codex",
                            prior_receipt_digest=prior_digest,
                            target_identity=desired_identity,
                        )
                        _write_journal(journal, saga)
                        recovered_transaction = False
                    if saga.target_identity != desired_identity:
                        empty_preparation = (
                            saga.phase == "prepared"
                            and not saga.repairs
                            and saga.plugin_change is None
                            and saga.cutover_entry is None
                            and not saga.harness_mutations
                            and not saga.target_receipt_digest
                        )
                        if empty_preparation:
                            journal.unlink(missing_ok=True)
                        else:
                            retired = saga
                            for mutation in reversed(saga.harness_mutations):
                                if mutation.phase in {"applied", "verified"}:
                                    rolled_back = self.service.adapters[
                                        mutation.harness
                                    ].rollback_reconcile(
                                        _deserialize_handle(mutation.handle),
                                        prior_desired,
                                    )
                                    if rolled_back.state not in {
                                        ResultState.READY,
                                        ResultState.DEGRADED,
                                    }:
                                        raise RuntimeError(
                                            f"{mutation.harness} changed-target "
                                            f"compensation is {rolled_back.state.value}"
                                        )
                                retired = replace(
                                    retired,
                                    phase="compensating",
                                    harness_mutations=tuple(
                                        replace(item, phase="rolled-back")
                                        if item.harness == mutation.harness
                                        else item
                                        for item in retired.harness_mutations
                                    ),
                                )
                                _write_journal(journal, retired)
                            saga = _recover_unfinished(journal, retired, config_path)
                            if saga is not None:
                                raise RuntimeError(
                                    "changed-target reconciliation journal was not retired"
                                )
                        saga = ReconciliationSaga(
                            "prepared",
                            "codex",
                            prior_receipt_digest=prior_digest,
                            target_identity=desired_identity,
                        )
                        _write_journal(journal, saga)
                    names = tuple(
                        name for name in previous.harnesses if name != "codex"
                    )
                    other_mutations = tuple(
                        item
                        for item in saga.harness_mutations
                        if item.harness != "codex"
                    )
                    if other_mutations:
                        if {item.harness for item in other_mutations} != set(names):
                            raise RuntimeError(
                                "cross-harness reconciliation participants are ambiguous"
                            )
                        changed_target = any(
                            _deserialize_handle(item.handle).target_identity
                            != _target_identity(desired)
                            for item in other_mutations
                        )
                        if changed_target:
                            for item in reversed(other_mutations):
                                if item.phase not in {"applied", "verified"}:
                                    continue
                                rolled_back = self.service.adapters[
                                    item.harness
                                ].rollback_reconcile(
                                    _deserialize_handle(item.handle), prior_desired
                                )
                                if rolled_back.state not in {
                                    ResultState.READY,
                                    ResultState.DEGRADED,
                                }:
                                    raise RuntimeError(
                                        f"{item.harness} changed-target compensation is "
                                        f"{rolled_back.state.value}"
                                    )
                                harness_checkpoint(item.harness, "rolled-back")
                            saga = replace(
                                saga,
                                phase="prepared",
                                harness_mutations=tuple(
                                    item
                                    for item in saga.harness_mutations
                                    if item.harness == "codex"
                                ),
                            )
                            _write_journal(journal, saga)
                    if not any(
                        item.harness != "codex" for item in saga.harness_mutations
                    ):
                        handles = []
                        for name in names:
                            handle = self.service.adapters[name].prepare_reconcile(
                                previous.harnesses[name], prior_desired, desired
                            )
                            if handle.target_identity != _target_identity(desired):
                                raise RuntimeError(
                                    f"{name} prepared an invalid reconciliation target"
                                )
                            handles.append(
                                HarnessMutationCheckpoint(
                                    name, "prepared", _serialize_handle(handle)
                                )
                            )
                        saga = replace(
                            saga,
                            phase="harness-prepared",
                            harness_mutations=(*saga.harness_mutations, *handles),
                        )
                        _write_journal(journal, saga)
                else:
                    prior_desired = desired
                codex_checkpoint = None
                if durable_codex:
                    codex_checkpoint = next(
                        (
                            item
                            for item in saga.harness_mutations
                            if item.harness == "codex"
                        ),
                        None,
                    )
                    if codex_checkpoint is not None and codex_checkpoint.phase in {
                        "applied",
                        "verified",
                    }:
                        rolled_back = adapter.rollback_reconcile(
                            _deserialize_handle(codex_checkpoint.handle), prior_desired
                        )
                        if rolled_back.state not in {
                            ResultState.READY,
                            ResultState.DEGRADED,
                        }:
                            raise RuntimeError(
                                "Codex restart compensation is "
                                f"{rolled_back.state.value}"
                            )
                        harness_checkpoint("codex", "rolled-back")
                        saga = replace(
                            saga,
                            harness_mutations=tuple(
                                item
                                for item in saga.harness_mutations
                                if item.harness != "codex"
                            ),
                        )
                        _write_journal(journal, saga)
                        codex_checkpoint = None
                    if codex_checkpoint is not None:
                        handle = _deserialize_handle(codex_checkpoint.handle)
                        if handle.target_identity != _desired_target_identity(desired):
                            raise RuntimeError(
                                "prepared Codex reconciliation target changed"
                            )
                    else:
                        codex_handle = adapter.prepare_reconcile(
                            previous.harnesses["codex"]
                            if previous is not None and "codex" in previous.harnesses
                            else HarnessReceipt(
                                "codex", "1", "prepared", (), (), {}, True
                            ),
                            prior_desired,
                            desired,
                        )
                        codex_checkpoint = HarnessMutationCheckpoint(
                            "codex", "prepared", _serialize_handle(codex_handle)
                        )
                        saga = replace(
                            saga,
                            phase="codex-prepared",
                            harness_mutations=(
                                *saga.harness_mutations,
                                codex_checkpoint,
                            ),
                        )
                        _write_journal(journal, saga)
                synchronized, synchronization_error = _converge_other_owned_harnesses(
                    self.service,
                    previous,
                    desired,
                    prior_desired,
                    detections,
                    harness_checkpoint,
                    tuple(
                        item
                        for item in saga.harness_mutations
                        if item.harness != "codex"
                    ),
                )
                if synchronization_error is not None:
                    raise _BootstrapAbort(synchronization_error, synchronized)

                if durable_codex:
                    assert codex_checkpoint is not None
                    harness_checkpoint("codex", "applying")
                    installed = adapter.apply_reconcile(
                        _deserialize_handle(codex_checkpoint.handle),
                        desired,
                        codex_retirement_checkpoint,
                    )
                    harness_checkpoint("codex", "applied")
                else:
                    installed = adapter.install(desired)
                inspected = (
                    adapter.verify_reconcile(
                        _deserialize_handle(codex_checkpoint.handle), desired
                    )
                    if durable_codex and codex_checkpoint is not None
                    else adapter.inspect(desired)
                )
                result = combine_results(installed, inspected)
                if not _converged(result):
                    raise _BootstrapAbort(
                        "Codex convergence did not reach READY", {"codex": result}
                    )
                harness_checkpoint("codex", "verified")
                if isinstance(adapter, CodexAdapter):
                    probed = adapter.probe_adhd_hook(desired)
                    result = combine_results(result, probed)
                    if probed.state is not ResultState.READY:
                        raise _BootstrapAbort(
                            "Codex SessionStart delivery probe did not reach READY",
                            {"codex": result},
                        )
                try:
                    parsed = config_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    parsed = None
                if parsed is not None:
                    if "i-have-adhd@i-have-adhd" in parsed:
                        change = prepare_plugin_enabled(
                            config_path, "i-have-adhd@i-have-adhd", False
                        )
                        saga = replace(
                            saga,
                            phase="upstream-prepared",
                            plugin_change=_serialize_change(change),
                        )
                        _write_journal(journal, saga)
                        apply_plugin_enabled(config_path, change)
                        saga = replace(saga, phase="upstream-disabled")
                        _write_journal(journal, saga)
                cutover = prepare_codex_skill_cutover(home, manifest_skills)
                if cutover.previous_checksum is not None:
                    saga = replace(
                        saga,
                        phase="cutover-prepared",
                        cutover_entry=_serialize_owned(cutover),
                    )
                    _write_journal(journal, saga)
                    apply_codex_skill_cutover(cutover, manifest_skills)
                    saga = replace(saga, phase="cutover-complete")
                    _write_journal(journal, saga)
                owned = list(result.owned_entries)
                if cutover.previous_checksum is not None:
                    owned.append(cutover)
                if change is not None and change.previous is not False:
                    owned.append(
                        OwnedEntry(
                            "plugin-enabled-state",
                            change.plugin_id,
                            "manifest",
                            str(config_path),
                            json.dumps(
                                {
                                    "previous": change.previous,
                                    "current": change.current,
                                    "written_sha256": change.written_sha256,
                                    "table_existed": change.table_existed,
                                    "separator_added": change.separator_added,
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        )
                    )
                result = HarnessResult(
                    result.harness,
                    result.state,
                    result.installed_plugin_ids,
                    result.capabilities,
                    result.errors,
                    result.warnings,
                    tuple(owned),
                )
                synchronized["codex"] = result
                receipt = build_receipt(
                    desired,
                    synchronized,
                    detections,
                    self.service.adapters,
                    ("claude", "codex", "gemini", "cursor", "antigravity", "devin"),
                    previous=previous,
                )
                receipt = receipt_for_persistence(self.service.receipt_path, receipt)
                saga = replace(
                    saga,
                    phase="receipt-prepared",
                    target_receipt_digest=receipt_digest(receipt),
                )
                _write_journal(journal, saga)
                try:
                    write_receipt_atomic(self.service.receipt_path, receipt)
                except Exception as write_error:
                    try:
                        visible = read_receipt(self.service.receipt_path)
                    except Exception as read_error:
                        rollback_allowed = False
                        raise RuntimeError(
                            "receipt persistence failed with unreadable visible state"
                        ) from read_error
                    visible_digest = (
                        receipt_digest(visible)
                        if visible is not None
                        else NO_PRIOR_RECEIPT_V1
                    )
                    if visible_digest == saga.target_receipt_digest:
                        # The rename reached the authoritative path; recovery must
                        # promote this prepared commit instead of compensating it.
                        receipt_committed = True
                    elif visible_digest != saga.prior_receipt_digest:
                        rollback_allowed = False
                        raise RuntimeError(
                            "receipt persistence failed with ambiguous visible state"
                        ) from write_error
                    raise
                receipt_committed = True
                saga = replace(saga, phase="committed")
                _write_journal(journal, saga)
                if cutover is not None and cutover.previous_checksum is not None:
                    commit_codex_skill_cutover(cutover)
                for item in saga.repairs:
                    remove_plugin_backup(CodexPluginBackup.from_dict(item.backup))
                for mutation in saga.harness_mutations:
                    for plugin in _deserialize_handle(mutation.handle).prior_inventory:
                        if plugin.rollback_data is not None:
                            remove_plugin_backup(
                                CodexPluginBackup.from_dict(plugin.rollback_data)
                            )
                journal.unlink(missing_ok=True)
                return report("bootstrap-sync", synchronized, notes)
        except Exception as exception:
            rollback_errors: list[str] = []
            if (
                cutover is not None
                and cutover.previous_checksum is not None
                and not receipt_committed
                and rollback_allowed
            ):
                try:
                    restore_codex_skills(cutover)
                except Exception as rollback_error:
                    rollback_errors.append(diagnostic(rollback_error))
            if change is not None and not receipt_committed and rollback_allowed:
                try:
                    rollback_plugin_enabled(config_path, change)
                except Exception as rollback_error:
                    rollback_errors.append(diagnostic(rollback_error))
            if saga is not None and not receipt_committed and rollback_allowed:
                try:
                    saga, harness_errors = _compensate_harness_mutations(
                        self.service, journal, saga, prior_desired, desired
                    )
                    rollback_errors.extend(harness_errors)
                    if not rollback_errors and saga.harness_mutations:
                        _retire_compensated_transaction(self.service, journal, saga)
                except Exception as rollback_error:
                    rollback_errors.append(diagnostic(rollback_error))
            message = diagnostic(exception)
            if rollback_errors:
                message += "; rollback BLOCKED: " + "; ".join(rollback_errors)
            results = (
                dict(exception.results)
                if isinstance(exception, _BootstrapAbort)
                else dict(synchronized)
            )
            results["codex"] = combine_results(
                results.get("codex", _blocked(message)), _blocked(message)
            )
            public_errors = (
                (str(exception),) if isinstance(exception, _BootstrapAbort) else ()
            )
            return report("bootstrap-sync", results, notes, public_errors)


def reconcile_owned_harnesses(service, receipt, desired, selected, apply=True):
    """Public bridge retained for receipt-aware callers."""
    del receipt, selected, apply
    return BootstrapSyncService(service).run(desired)


def _converged(result) -> bool:
    """Whether a harness result is good enough to commit.

    READY always converges. DEGRADED converges only when every contributor is a
    contract-declared degradation the harness can never satisfy (see
    adapters/convergence.py); a missing DEFAULT-tier capability still refuses.
    """
    if result.state is ResultState.READY:
        return True
    return result.state is ResultState.DEGRADED and not has_undeclared_degradation(
        result
    )
