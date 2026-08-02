"""Conservative handoff from bootstrap-owned files to native plugins.

Only the declarative inventory can name a path for migration.  This module is
intentionally independent of bootstrap so its recovery utility remains usable
after bootstrap has been retired.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from manifest_agent.adapters.base import Detection, HarnessAdapter
from manifest_agent.models import (
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    ResultState,
)
from manifest_agent.paths import XdgPaths
from manifest_agent.service_state import (
    ServiceReport,
    build_receipt,
    diagnostic,
    ordered,
    report,
)
from manifest_agent.state import read_receipt, write_receipt_atomic

_CATEGORIES = frozenset(
    {
        "skills",
        "agents",
        "guidance",
        "hooks",
        "permissions",
        "mcp",
        "scripts",
        "optional_tools",
        "configuration",
        "diagnostics",
        "updates",
        "uninstall",
    }
)
_DESTRUCTIVE_PROOFS = frozenset(
    {"symlink-target", "deploy-stamp", "generated-hash", "exact-marker"}
)
_FORBIDDEN_DESTINATIONS = ("manifest-core", "bootstrap", "shared-plugin")


@dataclass(frozen=True)
class OwnershipProof:
    """A proof required before a legacy output can be changed."""

    type: str
    value: str


@dataclass(frozen=True)
class LegacyInventoryEntry:
    """One exact legacy output and its native disposition."""

    id: str
    category: str
    path: str
    harnesses: tuple[str, ...]
    classification: str
    destination: str
    ownership_proof: OwnershipProof
    action: str
    recovery: str
    parity_test: str


@dataclass(frozen=True)
class LegacyInventory:
    """Validated, authoritative legacy ownership input."""

    categories: tuple[str, ...]
    entries: tuple[LegacyInventoryEntry, ...]


@dataclass(frozen=True)
class LegacyPathState:
    """The non-mutating classification of one discovered path."""

    path: str
    classification: str
    entry_id: str | None = None
    exists: bool = False
    ownership_proven: bool = False
    detail: str | None = None


@dataclass(frozen=True)
class LegacySnapshot:
    """Legacy scan output, including unrecognised files as user-owned."""

    entries: tuple[LegacyPathState, ...]

    def entry(self, path: str) -> LegacyPathState:
        for candidate in self.entries:
            if candidate.path == path:
                return candidate
        raise KeyError(path)


def load_legacy_inventory(path: Path | None = None) -> LegacyInventory:
    """Load and validate the inventory before any mutation is considered."""
    source = path or Path(__file__).with_name("data") / "legacy_inventory.yml"
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError("unable to load legacy ownership inventory") from error
    if not isinstance(document, dict):
        raise ValueError("legacy ownership inventory must be a mapping")
    categories = document.get("categories")
    rows = document.get("entries")
    if not isinstance(rows, list) or not rows:
        raise ValueError("legacy ownership inventory entries are required")
    entries = tuple(_decode_inventory_entry(row) for row in rows)
    if not isinstance(categories, list) or set(categories) != _CATEGORIES:
        raise ValueError("legacy ownership inventory categories are incomplete")
    identifiers = [entry.id for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("legacy ownership inventory IDs must be unique")
    return LegacyInventory(tuple(categories), entries)


def _decode_inventory_entry(value: Any) -> LegacyInventoryEntry:
    required = {
        "id",
        "category",
        "path",
        "harnesses",
        "classification",
        "destination",
        "ownership_proof",
        "action",
        "recovery",
        "parity_test",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("legacy ownership inventory entry has an invalid schema")
    proof = value["ownership_proof"]
    if not isinstance(proof, dict) or set(proof) != {"type", "value"}:
        raise ValueError("legacy ownership proof has an invalid schema")
    if not all(
        isinstance(value[key], str) and value[key]
        for key in required - {"harnesses", "ownership_proof"}
    ):
        raise ValueError("legacy ownership inventory strings must be non-empty")
    harnesses = value["harnesses"]
    if (
        not isinstance(harnesses, list)
        or not harnesses
        or not all(isinstance(name, str) and name for name in harnesses)
    ):
        raise ValueError("legacy ownership inventory harnesses are invalid")
    if value["category"] not in _CATEGORIES:
        raise ValueError("legacy ownership inventory entry has an unknown category")
    if value["action"] not in {"disable", "remove", "retain"}:
        raise ValueError("legacy ownership inventory entry has an invalid action")
    if (
        value["action"] in {"disable", "remove"}
        and proof.get("type") not in _DESTRUCTIVE_PROOFS
    ):
        raise ValueError("destructive legacy entry lacks ownership proof")
    if proof.get("type") == "generated-hash" and (
        not isinstance(proof.get("value"), str)
        or len(proof["value"]) != 64
        or any(char not in "0123456789abcdef" for char in proof["value"].lower())
    ):
        raise ValueError("generated-hash ownership proof must be an exact SHA-256")
    destination = value["destination"].lower()
    if any(forbidden in destination for forbidden in _FORBIDDEN_DESTINATIONS):
        raise ValueError("legacy ownership inventory has a forbidden destination")
    if not value["path"].startswith("~/") or ".." in Path(value["path"]).parts:
        raise ValueError("legacy ownership inventory paths must be HOME-relative")
    return LegacyInventoryEntry(
        value["id"],
        value["category"],
        value["path"],
        tuple(value["harnesses"]),
        value["classification"],
        value["destination"],
        OwnershipProof(proof["type"], proof["value"]),
        value["action"],
        value["recovery"],
        value["parity_test"],
    )


def scan_legacy_state(
    paths: XdgPaths,
    *,
    inventory: LegacyInventory | None = None,
    home: Path | None = None,
) -> LegacySnapshot:
    """Classify inventory paths and all unknown files beneath known homes.

    ``paths`` is accepted to make callers supply XDG context explicitly.  It is
    not used as a source of harness-home paths, which would couple migration to
    a coordinator-owned directory.
    """
    del paths
    source_home = (home or Path(os.environ.get("HOME", str(Path.home())))).resolve()
    source_inventory = inventory or load_legacy_inventory()
    known: dict[Path, LegacyInventoryEntry] = {
        _expand_home(entry.path, source_home): entry
        for entry in source_inventory.entries
    }
    states = [
        _state_for_entry(entry, target)
        for target, entry in sorted(known.items(), key=lambda item: str(item[0]))
    ]
    roots = sorted(
        {source_home / target.relative_to(source_home).parts[0] for target in known}
    )
    for root in roots:
        if not root.exists() or not root.is_dir() or root.is_symlink():
            continue
        for candidate in root.rglob("*"):
            if candidate in known or candidate.is_dir():
                continue
            states.append(
                LegacyPathState(
                    _display_path(candidate, source_home), "user-owned", exists=True
                )
            )
    return LegacySnapshot(tuple(sorted(states, key=lambda item: item.path)))


def _state_for_entry(entry: LegacyInventoryEntry, target: Path) -> LegacyPathState:
    exists = target.exists() or target.is_symlink()
    proven = exists and _proves_ownership(target, entry.ownership_proof)
    detail = None if not exists or proven else "ownership proof did not match"
    return LegacyPathState(
        entry.path,
        entry.classification if proven else ("absent" if not exists else "ambiguous"),
        entry.id,
        exists,
        proven,
        detail,
    )


def _proves_ownership(target: Path, proof: OwnershipProof) -> bool:
    if proof.type == "symlink-target":
        if not target.is_symlink():
            return False
        expected = _expand_home(proof.value, _home_for(target))
        observed = target.readlink()
        observed = (
            (target.parent / observed).resolve()
            if not observed.is_absolute()
            else observed.resolve()
        )
        return observed == expected.resolve()
    if proof.type == "exact-marker":
        # A substring marker can be copied into a user script. Legacy releases
        # did not issue a signed marker, so it is never sufficient to mutate.
        return False
    if proof.type == "deploy-stamp":
        home = _home_for(target)
        if proof.value.startswith("~/"):
            stamp = _expand_home(proof.value, home)
        else:
            try:
                harness_root = target.relative_to(home).parts[0]
            except ValueError:
                return False
            stamp = home / harness_root / proof.value
        return stamp.is_file() and "Manifest" in _read_text_limited(stamp)
    if proof.type == "generated-hash":
        if not target.is_file() or len(proof.value) != 64:
            return False
        if not all(char in "0123456789abcdef" for char in proof.value.lower()):
            return False
        return _file_digest(target) == proof.value.lower()
    return False


def _home_for(path: Path) -> Path:
    """Return the home prefix for a known ~/.foo legacy path."""
    for ancestor in (path, *path.parents):
        if ancestor.name.startswith(".") and ancestor.parent != ancestor:
            return ancestor.parent
    return Path.home()


def _read_text_limited(path: Path) -> str:
    try:
        return path.read_bytes()[: 1024 * 1024].decode("utf-8", errors="replace")
    except OSError:
        return ""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expand_home(value: str, home: Path) -> Path:
    if not value.startswith("~/"):
        raise ValueError("legacy paths must be HOME-relative")
    return home / value[2:]


def _display_path(path: Path, home: Path) -> str:
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


class MigrationService:
    """Perform a locked, rollback-capable one-writer migration."""

    def __init__(
        self,
        *,
        adapters: Mapping[str, HarnessAdapter],
        receipt_path: Path,
        paths: XdgPaths,
        lock_factory: Callable[[Path | None], Any],
        harness_order: Sequence[str],
        inventory: LegacyInventory | None = None,
        home: Path | None = None,
        event_log: list[str] | None = None,
    ) -> None:
        self.adapters = dict(adapters)
        self.receipt_path = receipt_path
        self.paths = paths
        self.lock_factory = lock_factory
        self.harness_order = tuple(harness_order)
        self.inventory = inventory or load_legacy_inventory()
        self.home = home or Path(os.environ.get("HOME", str(Path.home())))
        self.event_log = event_log
        self.state_path = paths.state / "migration.json"

    @classmethod
    def from_manifest_service(
        cls,
        service: Any,
        *,
        paths: XdgPaths,
        home: Path | None = None,
        event_log: list[str] | None = None,
    ) -> MigrationService:
        """Construct from the lifecycle service without a circular import."""
        return cls(
            adapters=service.adapters,
            receipt_path=service.receipt_path,
            paths=paths,
            lock_factory=service.lock_factory,
            harness_order=tuple(service.adapters),
            home=home,
            event_log=event_log,
        )

    def migrate(self, desired: DesiredState) -> ServiceReport:
        """Shadow-verify, hand off one writer, and commit only native success."""
        try:
            # Share the lifecycle lock: a normal install/uninstall cannot run
            # while legacy output is temporarily quarantined.
            with self.lock_factory(self.receipt_path.parent / "install.lock"):
                completed = read_receipt(self.receipt_path)
                selected = self._selected(desired)
                if self._already_migrated(completed, selected):
                    return report("migrate", {})
                return self._migrate_locked(desired, selected, completed)
        # constitution: exempt C-ERR -- migration boundary returns a redacted report.
        except Exception as exception:
            return report("migrate", {}, errors=(diagnostic(exception),))

    def _selected(self, desired: DesiredState) -> tuple[str, ...]:
        requested = desired.requested_harnesses
        candidates = (
            self.harness_order if not requested or requested == ("all",) else requested
        )
        return tuple(
            name
            for name in self.harness_order
            if name in candidates and name in self.adapters
        )

    def _already_migrated(
        self, receipt: InstallationReceipt | None, selected: Sequence[str]
    ) -> bool:
        return bool(
            receipt is not None
            and receipt.migration_complete
            and all(
                name in receipt.harnesses and receipt.harnesses[name].verified
                for name in selected
            )
        )

    def _migrate_locked(
        self,
        desired: DesiredState,
        selected: Sequence[str],
        previous: InstallationReceipt | None,
    ) -> ServiceReport:
        unavailable: dict[str, HarnessResult] = {}
        active: list[str] = []
        detections: dict[str, Detection] = {}
        for name in selected:
            locked = self._harness_session_locked(name)
            if locked is not None:
                unavailable[name] = HarnessResult(
                    name, ResultState.BLOCKED, (), {}, errors=(locked,)
                )
                continue
            detection = self.adapters[name].detect()
            detections[name] = detection
            if detection.present:
                active.append(name)
            else:
                unavailable[name] = HarnessResult(
                    name,
                    ResultState.BLOCKED,
                    (),
                    {},
                    errors=(detection.reason or "harness CLI not present",),
                )
        if unavailable:
            return report("migrate", ordered(unavailable, self.harness_order))
        state = self._load_or_snapshot(active, desired)
        results: dict[str, HarnessResult] = {}
        for name in active:
            phase = state["harnesses"].get(name, {}).get("phase", "snapshot")
            if phase == "committed":
                results[name] = self.adapters[name].inspect(desired)
                continue
            result = self._migrate_harness(name, desired, state)
            results[name] = result
            if result.state is not ResultState.READY:
                return report("migrate", ordered(results, self.harness_order))
        receipt = build_receipt(
            desired,
            results,
            detections,
            self.adapters,
            self.harness_order,
            previous=previous,
        )
        backup = state["backup"]
        write_receipt_atomic(
            self.receipt_path,
            InstallationReceipt(
                receipt.schema_version,
                receipt.coordinator_version,
                receipt.release_version,
                receipt.source_commit,
                receipt.source_dirty,
                receipt.archive_sha256,
                receipt.bundle_checksums,
                receipt.selected_optional,
                receipt.harnesses,
                backup,
            ),
        )
        self._event("commit-receipt")
        for name in active:
            state["harnesses"][name]["phase"] = "committed"
        self._write_state(state)
        return report("migrate", ordered(results, self.harness_order))

    def _harness_session_locked(self, harness: str) -> str | None:
        """Refuse a handoff while a known harness session lock is held."""
        roots = {
            "claude": self.home / ".claude",
            "codex": self.home / ".codex",
            "gemini": self.home / ".gemini",
            "cursor": self.home / ".cursor",
            "antigravity": self.home / ".antigravity",
            "devin": self.home / ".config" / "devin",
        }
        root = roots[harness]
        for candidate in (root / ".lock", root / "session.lock"):
            if not candidate.is_file():
                continue
            descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return f"{harness} has an active session lock at {candidate}; close it before migrating"
                finally:
                    with suppress(OSError):
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        return None

    def _load_or_snapshot(
        self, harnesses: Sequence[str], desired: DesiredState
    ) -> dict[str, Any]:
        existing = self._read_state()
        if existing is not None:
            if existing.get("identity") != _migration_identity(desired):
                raise ValueError(
                    "migration recovery state targets a different release, checksum, options, or harness scope"
                )
            backup = Path(existing["backup"])
            for name in harnesses:
                if name not in existing["harnesses"]:
                    existing["harnesses"][name] = {
                        "phase": "snapshot",
                        "entries": self._snapshot_harness(name, backup),
                    }
            self._write_recovery(backup, existing)
            self._write_state(existing)
            return existing
        timestamp = f"{int(time.time() * 1000)}-{os.getpid()}"
        backup = self.paths.state / "migration-backups" / timestamp
        backup.mkdir(parents=True, mode=0o700)
        state: dict[str, Any] = {
            "schema_version": 1,
            "backup": str(backup),
            "identity": _migration_identity(desired),
            "harnesses": {},
        }
        for name in harnesses:
            records = self._snapshot_harness(name, backup)
            state["harnesses"][name] = {"phase": "snapshot", "entries": records}
        self._write_recovery(backup, state)
        self._write_state(state)
        self._event("snapshot-legacy")
        return state

    def _snapshot_harness(self, harness: str, backup: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for entry in self.inventory.entries:
            if harness not in entry.harnesses or entry.action not in {
                "disable",
                "remove",
            }:
                continue
            source = _expand_home(entry.path, self.home)
            if not (source.exists() or source.is_symlink()):
                continue
            if not _proves_ownership(source, entry.ownership_proof):
                raise ValueError(
                    f"ownership proof is ambiguous for {entry.path}; user action is required"
                )
            artifact = backup / "files" / harness / entry.id
            _copy_path(source, artifact)
            records.append(
                {
                    "id": entry.id,
                    "path": entry.path,
                    "artifact": str(artifact.relative_to(backup)),
                    "mode": stat.S_IMODE(source.lstat().st_mode),
                    "link_target": os.readlink(source) if source.is_symlink() else None,
                    "sha256": _path_digest(source),
                    "disabled_path": None,
                }
            )
        return records

    def _migrate_harness(
        self, harness: str, desired: DesiredState, state: dict[str, Any]
    ) -> HarnessResult:
        adapter = self.adapters[harness]
        phase = state["harnesses"][harness]["phase"]
        try:
            if phase == "snapshot":
                shadow = self.paths.state / "migration-shadows" / harness
                installed = self._shadow_call(adapter, "install", desired, shadow)
                if installed.state is not ResultState.READY:
                    return installed
                state["harnesses"][harness]["phase"] = "shadow-installed"
                self._write_state(state)
                phase = "shadow-installed"
            if phase == "shadow-installed":
                shadow = self.paths.state / "migration-shadows" / harness
                verified = self._shadow_call(adapter, "inspect", desired, shadow)
                if verified.state is not ResultState.READY:
                    return verified
                state["harnesses"][harness]["phase"] = "shadow-verified"
                self._write_state(state)
                phase = "shadow-verified"
            if phase == "shadow-verified":
                self._disable_legacy(harness, state)
                state["harnesses"][harness]["phase"] = "legacy-disabled"
                self._write_state(state)
                phase = "legacy-disabled"
            if phase == "legacy-disabled":
                self._event("native-install")
                installed = adapter.install(desired)
                if installed.state is not ResultState.READY:
                    rollback_error = self._rollback_harness(
                        harness, state, adapter, installed
                    )
                    return _with_rollback_error(installed, rollback_error)
                state["harnesses"][harness]["phase"] = "native-installed"
                self._write_state(state)
                phase = "native-installed"
            if phase == "native-installed":
                self._event("native-verify")
                verified = adapter.inspect(desired)
                if verified.state is not ResultState.READY:
                    rollback_error = self._rollback_harness(
                        harness, state, adapter, verified
                    )
                    return _with_rollback_error(verified, rollback_error)
                self._remove_disabled(harness, state)
                state["harnesses"][harness]["phase"] = "native-verified"
                self._write_state(state)
                return verified
            if phase == "native-verified":
                return adapter.inspect(desired)
            raise ValueError(f"unknown migration phase for {harness}: {phase}")
        except Exception as exception:
            if phase in {"legacy-disabled", "native-installed"}:
                self._rollback_harness(harness, state, adapter, None)
            return HarnessResult(
                harness, ResultState.BLOCKED, (), {}, errors=(diagnostic(exception),)
            )

    def _shadow_call(
        self, adapter: HarnessAdapter, operation: str, desired: DesiredState, home: Path
    ) -> HarnessResult:
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        named = getattr(adapter, f"shadow_{operation}", None)
        self._event("shadow-verify" if operation == "inspect" else "shadow-install")
        if named is not None:
            return named(desired, home)
        shadow = copy.copy(adapter)
        environment = dict(getattr(adapter, "_env", None) or {})
        environment.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local" / "share"),
                "XDG_STATE_HOME": str(home / ".local" / "state"),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
        )
        if not hasattr(shadow, "_env"):
            return HarnessResult(
                adapter.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=("adapter cannot create an isolated migration home",),
            )
        shadow._env = environment
        return getattr(shadow, operation)(desired)

    def _disable_legacy(self, harness: str, state: dict[str, Any]) -> None:
        backup = Path(state["backup"])
        for record in state["harnesses"][harness]["entries"]:
            source = _expand_home(record["path"], self.home)
            if not (source.exists() or source.is_symlink()):
                continue
            disabled = source.parent / f".{source.name}.manifest-disabled-{backup.name}"
            if disabled.exists() or disabled.is_symlink():
                raise ValueError(f"migration quarantine already exists: {disabled}")
            # Record the intended rename before it occurs so recovery can tell a
            # crash before the rename from one immediately after it.
            record["pending_disabled_path"] = str(disabled)
            self._write_state(state)
            os.replace(source, disabled)
            record["disabled_path"] = str(disabled)
            record.pop("pending_disabled_path", None)
            self._write_state(state)
        self._event("disable-legacy")

    def _remove_disabled(self, harness: str, state: dict[str, Any]) -> None:
        for record in state["harnesses"][harness]["entries"]:
            disabled = record.get("disabled_path")
            if disabled:
                _remove_path(Path(disabled))

    def _rollback_harness(
        self,
        harness: str,
        state: dict[str, Any],
        adapter: HarnessAdapter,
        result: HarnessResult | None,
    ) -> str | None:
        uninstall_error = None
        if result is not None:
            provisional = HarnessReceipt(
                harness,
                getattr(adapter, "adapter_version", "unknown"),
                "unknown",
                result.installed_plugin_ids,
                result.owned_entries,
                result.capabilities,
                False,
                result.errors or ("native migration verification failed",),
            )
            try:
                adapter.uninstall(provisional)
            except Exception as exception:
                uninstall_error = diagnostic(exception)
        if uninstall_error is not None:
            # Restoring legacy output while an unverified native copy remains
            # would create two writers. Leave the durable quarantine in place.
            return uninstall_error
        backup = Path(state["backup"])
        for record in state["harnesses"][harness]["entries"]:
            source = _expand_home(record["path"], self.home)
            disabled = record.get("disabled_path")
            if disabled and (Path(disabled).exists() or Path(disabled).is_symlink()):
                if source.exists() or source.is_symlink():
                    raise ValueError(
                        f"cannot restore {record['path']}: path changed during migration"
                    )
                os.replace(Path(disabled), source)
                continue
            if not (source.exists() or source.is_symlink()):
                _copy_path(backup / record["artifact"], source)
        state["harnesses"][harness]["phase"] = "snapshot"
        self._write_state(state)
        return uninstall_error

    def _read_state(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("unable to read migration recovery state") from error
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("migration recovery state has an invalid schema")
        return value

    def _write_state(self, value: Mapping[str, Any]) -> None:
        _write_json_atomic(self.state_path, value)

    def _write_recovery(self, backup: Path, state: Mapping[str, Any]) -> None:
        _write_json_atomic(backup / "recovery.json", state)
        restore = backup / "restore.py"
        restore.write_text(_RESTORE_PROGRAM, encoding="utf-8")
        restore.chmod(0o700)

    def _event(self, event: str) -> None:
        if self.event_log is not None:
            self.event_log.append(event)


def _copy_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if source.is_symlink():
        destination.symlink_to(source.readlink())
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _path_digest(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    if path.is_file():
        return _file_digest(path)
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*")):
        digest.update(candidate.relative_to(path).as_posix().encode())
        if candidate.is_symlink():
            digest.update(os.fsencode(os.readlink(candidate)))
        elif candidate.is_file():
            digest.update(_file_digest(candidate).encode())
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


_RESTORE_PROGRAM = '''#!/usr/bin/env python3
"""Restore a Manifest migration backup without importing Manifest or bootstrap."""
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = json.loads((ROOT / "recovery.json").read_text(encoding="utf-8"))
HOME = Path(os.environ["HOME"])

def target(value):
    if not value.startswith("~/") or ".." in Path(value).parts:
        raise ValueError("unsafe recovery path")
    return HOME / value[2:]

def digest(path):
    import hashlib
    if path.is_symlink(): return hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    if path.is_file(): return hashlib.sha256(path.read_bytes()).hexdigest()
    value = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        value.update(child.relative_to(path).as_posix().encode())
    return value.hexdigest()

for harness in STATE["harnesses"].values():
    for entry in harness["entries"]:
        source = ROOT / entry["artifact"]
        destination = target(entry["path"])
        # Never overwrite a post-crash user/native path. A matching snapshot is
        # already restored; any other existing value requires manual recovery.
        if destination.exists() or destination.is_symlink():
            if digest(destination) != entry["sha256"]:
                raise RuntimeError("refusing to overwrite changed path: " + str(destination))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink(): destination.symlink_to(source.readlink())
        elif source.is_dir(): shutil.copytree(source, destination, symlinks=True)
        else: shutil.copy2(source, destination, follow_symlinks=False)
'''


def _migration_identity(desired: DesiredState) -> dict[str, object]:
    return {
        "release_version": desired.release_version,
        "source_commit": desired.source_commit,
        "archive_sha256": desired.archive_sha256,
        "selected_optional": sorted(desired.selected_optional),
        "requested_harnesses": list(desired.requested_harnesses),
    }


def _with_rollback_error(
    result: HarnessResult, rollback_error: str | None
) -> HarnessResult:
    if rollback_error is None:
        return result
    return HarnessResult(
        result.harness,
        ResultState.BLOCKED,
        result.installed_plugin_ids,
        result.capabilities,
        errors=(*result.errors, f"native cleanup failed: {rollback_error}"),
        warnings=result.warnings,
        owned_entries=result.owned_entries,
    )


__all__ = [
    "LegacyInventory",
    "LegacyInventoryEntry",
    "LegacyPathState",
    "LegacySnapshot",
    "MigrationService",
    "OwnershipProof",
    "load_legacy_inventory",
    "scan_legacy_state",
]
