"""Authorized observer provisioning, generation ownership, and crash recovery."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from manifest_agent import observer_runtime_transactions as _transactions
from manifest_agent._observer_store import (
    STORE_DOMAIN as STORE_DOMAIN,
)
from manifest_agent._observer_store import (
    _claim_store,
    _finish_store,
    _inode,
    _release_store,
    _safe_parents,
    _store_owner,
    _store_path,
    _write_signed,
)
from manifest_agent.checks import toolchain
from manifest_agent.checks.toolchain_env_digest import trusted_python_provider
from manifest_agent.checks.toolchain_materialize import (
    MaterializeContext,
    _run,
    materialize_python_env,
    relocate_python_launchers,
)
from manifest_agent.checks.toolchain_provision import provision
from manifest_agent.checks.toolchain_provision_store import _remove_tree_at
from manifest_agent.observer_runtime_identity import (
    ObserverBinding,
    ObserverRuntimeError,
    authority,
    canonical,
    digest,
    environment_inventory,
    forbidden_root,
    generation_paths,
    observer_key_path,
    platform_id,
    read_regular,
    read_signed,
    resolve_observer_runtime,
    runtime_roots,
    sign,
    validate_record,
)
from manifest_agent.observer_runtime_transactions import (
    PENDING_DOMAIN,
    _pending_path,
    _recover,
    _recover_retirements,
    _reference,
    _referenced,
    _retire_generation,
)
from manifest_agent.observer_runtime_transactions import (
    queue_observer_cleanup as queue_observer_cleanup,
)
from manifest_agent.ownership import ensure_bootstrap_journal_authority
from manifest_agent.service_state import with_source_fingerprints
from manifest_agent.state import (
    _write_private_json_atomic,
    installation_lock,
    read_receipt,
    receipt_digest,
    receipt_for_persistence,
    write_receipt_atomic,
)

PROJECT = "plugins/manifest-workspace/runtime/observer"


def _observer_authority(receipt: Path) -> Path:
    key = observer_key_path(os.environ)
    data, state = runtime_roots(os.environ)
    _safe_parents(state)
    # A legacy receipt with no observer state can initialize this distinct
    # authority. Any durable observer data means a missing key is authority loss.
    durable = any(p != key and p.name != "observer.lock" for p in state.iterdir())
    durable = durable or (data.exists() and any(data.iterdir()))
    ensure_bootstrap_journal_authority(
        key, receipt_exists=durable, journal_exists=_pending_path(receipt).exists()
    )
    authority(key)
    return key


def requires_observer(desired) -> bool:
    return any(
        contract.name == "manifest-workspace"
        and any(
            item.id == "native-observer-runtime"
            for item in getattr(contract.components, "runtime", ())
        )
        for contract in desired.contracts
    )


def _source_unchanged(desired) -> None:
    if not desired.source_workspace_sha256 or not desired.source_bundle_checksums:
        raise ValueError("observer source fingerprint is missing")
    current = with_source_fingerprints(desired)
    if (
        current.source_workspace_sha256 != desired.source_workspace_sha256
        or current.source_bundle_checksums != desired.source_bundle_checksums
        or current.source_catalog_sha256 != desired.source_catalog_sha256
    ):
        raise ValueError("observer source fingerprint changed during staging")


def _binding(desired) -> ObserverBinding:
    project = desired.release_root / PROJECT
    checksums = dict(desired.source_bundle_checksums)
    return ObserverBinding(
        desired.source_commit,
        desired.archive_sha256,
        checksums["manifest-workspace"],
        digest(read_regular(project / "uv.lock")),
        platform_id(),
    )


def _provider(project: Path, platform: str) -> dict:
    pinned = trusted_python_provider().lock_record()
    return {"path": str(Path(sys.executable).resolve(strict=True)), **pinned}


def _smoke(env_root: Path, release_root: Path, receipt_path: Path) -> None:
    # Exercise the installed import and real public observation JSON producer.
    # First-install absence is an honest BLOCKED report, never fabricated READY.
    code = (
        "import json, pathlib, sys, manifest_agent; "
        "assert pathlib.Path(manifest_agent.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix)); "
        "from manifest_agent.native_observation import observe_native_state; "
        "r=observe_native_state(source_root=pathlib.Path(sys.argv[1]), receipt_path=pathlib.Path(sys.argv[2])); "
        "assert r['operation']=='reconcile' and isinstance(r['harnesses'], dict); "
        "print(json.dumps(r))"
    )
    _run(
        [
            str(env_root / "bin/python"),
            "-I",
            "-B",
            "-c",
            code,
            str(release_root),
            str(receipt_path),
        ],
        cwd=env_root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "UV_NO_SYNC": "1"},
    )


def _check_observer_locations(desired) -> None:
    """Preflight every write namespace before even creating the observer lock."""
    protected = [desired.release_root]
    if Path(desired.source).is_absolute():
        protected.append(Path(desired.source))
    protected.extend(
        desired.bundle_path(contract.name) for contract in desired.all_contracts
    )
    data, state = runtime_roots(os.environ)
    # Check the namespaces first: unsafe XDG settings must not require reading
    # project metadata, creating authority state, or recovering old transactions.
    for path in (data, state):
        if violated := forbidden_root(path, *protected):
            raise ObserverRuntimeError(
                f"observer runtime must not resolve inside {violated}"
            )
    binding = _binding(desired)
    provider = _provider(desired.release_root / PROJECT, binding.platform)
    root, record = generation_paths(binding, provider, os.environ)
    store = _store_path(desired.release_root / PROJECT, binding.platform, *protected)
    for path in (store, root, root.parent, record.parent):
        if violated := forbidden_root(path, *protected):
            raise ObserverRuntimeError(
                f"observer runtime must not resolve inside {violated}"
            )


def prepare_observer_runtime(desired, *, receipt_path: Path) -> ObserverBinding:
    _check_observer_locations(desired)
    _, state = runtime_roots(os.environ)
    _safe_parents(state)
    with installation_lock(state / "observer.lock"):
        return _prepare_observer_runtime(desired, receipt_path=receipt_path)


def _prepare_observer_runtime(desired, *, receipt_path: Path) -> ObserverBinding:
    """Prepare only inside an authorized service operation holding its install lock."""
    _check_observer_locations(desired)
    _source_unchanged(desired)
    binding = _binding(desired)
    project = desired.release_root / PROJECT
    provider = _provider(project, binding.platform)
    root, record_path = generation_paths(binding, provider, os.environ)
    key = _observer_authority(receipt_path)
    _recover_retirements(key)
    _recover(receipt_path, key)
    _reference(receipt_path, binding, key)
    if (
        root.exists()
        or root.is_symlink()
        or record_path.exists()
        or record_path.is_symlink()
    ):
        if (
            root.is_symlink()
            or record_path.is_symlink()
            or not root.exists()
            or not record_path.exists()
        ):
            raise ValueError(
                "unowned observer generation; refusing adoption or replacement"
            )
        record = read_signed(record_path, key)
        validate_record(record, binding, root)
        store = _store_path(project, binding.platform)
        marker = _store_owner(store, key)
        owner = f"{binding.id}/{digest(canonical(provider))}"
        if marker["phase"] != "ready" or owner not in marker["owners"]:
            raise ValueError("observer cache is not owned by this provider generation")
        lock = json.loads(read_regular(project / "uv-toolchain.lock.json"))
        resolved = toolchain.resolve(
            "store:uv/bin/uv",
            lock=lock,
            store=store,
            platform=binding.platform,
            repo_root=desired.release_root,
        )
        if isinstance(resolved, toolchain.BlockedReason):
            raise ValueError(resolved.reason)
        _source_unchanged(desired)
        return binding
    _stage_observer(desired, binding, provider, receipt_path)
    return binding


@contextmanager
def _observer_stage(path: Path):
    """Clean only the transaction directory this operation actually created."""
    import stat

    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.mkdir(path.name, mode=0o700, dir_fd=parent)
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or os.listdir(descriptor)
            ):
                raise ValueError(
                    "unowned observer stage; refusing adoption or deletion"
                )
            inode = [info.st_dev, info.st_ino]
            try:
                yield path, inode
            finally:
                if path.exists() or path.is_symlink():
                    if path.is_symlink() or not path.is_dir() or _inode(path) != inode:
                        raise ValueError(
                            "observer pending stage was replaced; foreign bytes preserved"
                        )
                    _remove_tree_at(parent, path.name, expected_inode=inode)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def _stage_observer(desired, binding, provider, receipt_path):
    project = desired.release_root / PROJECT
    root, record_path = generation_paths(binding, provider, os.environ)
    key = observer_key_path(os.environ)
    _safe_parents(root.parent)
    store = _store_path(project, binding.platform)
    owner = f"{binding.id}/{digest(canonical(provider))}"
    stage_path = root.parent / f".{root.name}.{os.getpid()}.staging"
    if stage_path.exists() or stage_path.is_symlink():
        raise ValueError("unowned observer stage; refusing replacement")
    try:
        with _observer_stage(stage_path) as (stage, stage_inode):
            pending = {
                "receipt": str(receipt_path.absolute()),
                "binding": asdict(binding),
                "provider": provider,
                "stage": stage.name,
                "pid": os.getpid(),
                "inode": stage_inode,
                "owner": owner,
                "store_lock_sha256": store.parent.name,
                "release_root": str(desired.release_root),
            }
            _write_signed(_pending_path(receipt_path), pending, key, PENDING_DOMAIN)
            _claim_store(store, owner, key)
            # uv may replace its environment directory. Authenticate the stable
            # transaction parent instead, including across a hard exit in uv.
            environment = stage / "environment"
            record = _materialize_observer(
                desired, environment, root, receipt_path, provider
            )
            if stage.is_symlink() or _inode(stage) != pending["inode"]:
                raise ValueError("observer pending stage was replaced")
            if root.exists() or root.is_symlink():
                raise ValueError(
                    "observer generation appeared during staging; refusing replacement"
                )
            _safe_parents(record_path.parent)
            signed = sign(record, key)
            validate_record(signed, binding, environment)
            _write_private_json_atomic(record_path, signed)
            _finish_store(store, owner, key)
            os.replace(environment, root)
    except BaseException:
        # A published, attested generation survives; a missing generation
        # relinquishes only its authenticated store owner.
        _recover(receipt_path, key)
        raise
    _pending_path(receipt_path).unlink()


def _materialize_observer(desired, stage, root, receipt_path, provider):
    binding = _binding(desired)
    store = _store_path(desired.release_root / PROJECT, binding.platform)
    lock = json.loads(
        read_regular(desired.release_root / PROJECT / "uv-toolchain.lock.json")
    )
    outcomes = provision(
        lock,
        store,
        platform=binding.platform,
        only=frozenset({"uv"}),
        repo_root=desired.release_root,
        env=os.environ,
    )
    if len(outcomes) != 1 or outcomes[0].status != "provisioned":
        raise ValueError(f"observer locked uv provisioning failed: {outcomes}")
    context = MaterializeContext(
        lock,
        store,
        binding.platform,
        desired.release_root,
        os.environ,
        {k: v for k, v in provider.items() if k != "path"},
    )
    materialize_python_env(
        context, stage, project_relative=PROJECT, build_from_locked_environment=True
    )
    relocate_python_launchers(stage, root)
    _smoke(stage, desired.release_root, receipt_path)
    files = environment_inventory(stage, provider)
    _source_unchanged(desired)
    record = {
        "schema_version": 1,
        "binding": asdict(binding),
        "provider": provider,
        "files": files,
        "environment_sha256": digest(canonical(files)),
    }
    return record


class ObserverTransaction:
    """Service seam preserving prior generations on failed native operations."""

    def __init__(self, desired, receipt_path):
        self.desired, self.receipt_path = desired, receipt_path
        self.created = False
        self.committed = False

    def __enter__(self):
        if requires_observer(self.desired):
            _source_unchanged(self.desired)
            self.binding = _binding(self.desired)
            self.provider = _provider(
                self.desired.release_root / PROJECT, self.binding.platform
            )
            self.root, self.record_path = generation_paths(
                self.binding, self.provider, os.environ
            )
            self.created = not self.root.exists()
            prepare_observer_runtime(self.desired, receipt_path=self.receipt_path)
        return self

    def persist(self, receipt):
        _source_unchanged(self.desired)
        target = receipt_for_persistence(self.receipt_path, receipt)
        try:
            write_receipt_atomic(self.receipt_path, target)
        except Exception:
            try:
                visible = read_receipt(self.receipt_path)
            except Exception as read_error:
                # Ambiguous publication must preserve the environment; deleting
                # it could break a receipt whose rename already reached disk.
                self.committed = True
                raise RuntimeError(
                    "observer receipt publication is unreadable; generation preserved"
                ) from read_error
            self.committed = visible is not None and receipt_digest(
                visible
            ) == receipt_digest(target)
            raise
        self.committed = True

    def __exit__(self, kind, value, traceback):
        if not self.created or self.committed:
            return False
        _, state = runtime_roots(os.environ)
        with installation_lock(state / "observer.lock"):
            return self._rollback()

    def _rollback(self):
        if self.created and not self.committed:
            key = observer_key_path(os.environ)
            try:
                selected = read_receipt(self.receipt_path)
            except Exception:
                # Never delete when publication cannot be classified.
                return False
            if selected is not None and (
                selected.source_commit == self.binding.source_commit
                and selected.archive_sha256 == self.binding.archive_sha256
                and selected.bundle_checksums.get("manifest-workspace")
                == self.binding.bundle_sha256
            ):
                return False
            if _referenced(self.binding, self.receipt_path, key):
                return False
            record = read_signed(self.record_path, key)
            _retire_generation(self.record_path, record, key, receipt=self.receipt_path)
            store = _store_path(
                self.desired.release_root / PROJECT, self.binding.platform
            )
            _release_store(
                store, f"{self.binding.id}/{digest(canonical(self.provider))}", key
            )
        return False


def remove_observer(receipt_path: Path) -> None:
    _transactions._remove_tree_at = _remove_tree_at
    _transactions.remove_observer(receipt_path)


__all__ = ["ObserverBinding", "prepare_observer_runtime", "resolve_observer_runtime"]
