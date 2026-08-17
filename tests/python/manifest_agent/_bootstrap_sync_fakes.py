"""Fake adapters and command runners for the bootstrap-sync saga suites."""

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.adapters.base import Detection
from manifest_agent.adapters.capability_lifecycle import CapabilityAdapterMixin
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.codex_plugin_backup import (
    capture_owned_file_backup,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    AdapterMutationHandle,
    CommandResult,
    HarnessResult,
    ResultState,
)
from manifest_agent.ownership import owned_file_ownership
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
)


class _RetirementRunner:
    def __init__(self, installed: Path, marketplace_root: Path) -> None:
        self.installed = installed
        self.marketplace_root = marketplace_root
        self.log: list[tuple[str, ...]] = []

    def _row(self) -> dict[str, object]:
        return {
            "pluginId": "manifest-retired@manifest",
            "version": "0.1.0",
            "enabled": True,
            "installed": True,
            "source": {"path": str(self.installed)},
        }

    def _rows(self) -> list[dict[str, object]]:
        rows = [
            {
                "pluginId": f"{name}@manifest",
                "version": "1.0.0",
                "enabled": True,
                "installed": True,
                "source": {"path": str(self.marketplace_root / "plugins" / name)},
            }
            for name in DOMAIN_BUNDLES
        ]
        if self.installed.exists():
            rows.append(self._row())
        return rows

    def run(self, argv, *, env=None) -> CommandResult:
        del env
        command = tuple(argv)
        self.log.append(command)
        if command[1:] == ("plugin", "marketplace", "list", "--json"):
            stdout = json.dumps(
                {
                    "marketplaces": [
                        {
                            "name": "manifest",
                            "root": str(self.marketplace_root),
                            "marketplaceSource": {
                                "sourceType": "local",
                                "source": str(self.marketplace_root),
                            },
                        }
                    ]
                }
            )
        elif command[1:] == ("plugin", "list", "--json"):
            stdout = json.dumps({"installed": self._rows()})
        elif command[1:] == (
            "plugin",
            "remove",
            "manifest-retired@manifest",
            "--json",
        ):
            shutil.rmtree(self.installed)
            stdout = json.dumps(
                {
                    "pluginId": "manifest-retired@manifest",
                    "name": "manifest-retired",
                    "marketplaceName": "manifest",
                }
            )
        else:
            raise AssertionError(f"unexpected Codex command: {command}")
        return CommandResult(command, 0, stdout, "")


class _RetirementCodexAdapter(CodexAdapter):
    def detect(self) -> Detection:
        return Detection(True, "codex", "1.0.0")


class _ProbeAdapter(CodexAdapter):
    def __init__(self, probe_state=ResultState.READY):
        self.calls = []
        self.probe_state = probe_state
        self.adapter_version = "1"

    def detect(self):
        from manifest_agent.adapters.base import Detection

        self.calls.append("detect")
        return Detection(True, "codex", "1.0.0")

    def install_with_checkpoints(self, desired, checkpoint=None):
        del desired, checkpoint
        self.calls.append("install")
        return HarnessResult("codex", ResultState.READY, (), {})

    def inspect(self, desired):
        del desired
        self.calls.append("inspect")
        return HarnessResult("codex", ResultState.READY, (), {})

    def probe_adhd_hook(self, desired):
        del desired
        self.calls.append("probe")
        return HarnessResult(
            "codex",
            self.probe_state,
            (),
            {"addon:manifest-i-have-adhd:session-start": "verified"}
            if self.probe_state is ResultState.READY
            else {},
            errors=("probe failed",)
            if self.probe_state is not ResultState.READY
            else (),
        )


class ArchiveRollbackAdapter(CapabilityAdapterMixin, FakeAdapter):
    """Owned-file adapter whose rollback restores the exact captured archive."""

    target_bytes = b"release two\n"

    def __init__(self, target: Path, env: dict[str, str]) -> None:
        FakeAdapter.__init__(self, "claude", harness_result("claude"))
        self._target = target
        self._env = env
        self.prepared_backup = None

    def prepare_reconcile(self, receipt, prior_desired, desired):
        del receipt, prior_desired
        backup, mode, digest = capture_owned_file_backup(self._target, self._env)
        self.prepared_backup = backup
        prior_row = {
            "path": str(self._target),
            "type": "file",
            "mode": mode,
            "digest": digest,
            "restore": {"archive": backup.to_dict()},
        }
        target_row = {
            "path": str(self._target),
            "type": "file",
            "mode": mode,
            "digest": hashlib.sha256(self.target_bytes).hexdigest(),
        }
        return AdapterMutationHandle(
            2,
            self.name,
            self.adapter_version,
            bootstrap_module._target_identity(desired),
            (),
            (),
            prior_cas=self._reconcile_cas((), {}, (prior_row,)),
            target_cas=self._reconcile_cas((), {}, (target_row,)),
            prior_owned_files=(prior_row,),
            target_owned_files=(target_row,),
        )

    def apply_reconcile(self, handle, desired):
        del handle, desired
        self.calls.append("apply")
        self._target.write_bytes(self.target_bytes)
        return harness_result(self.name)

    def verify_reconcile(self, handle, desired):
        del desired
        return (
            harness_result(self.name)
            if self.classify_reconcile_state(handle, None) == "target"
            else harness_result(
                self.name,
                ResultState.BLOCKED,
                errors=("target bytes are not visible",),
            )
        )

    def classify_reconcile_state(self, handle, desired):
        del desired
        observed = self._observable_owned_file(self._observe_owned_file(self._target))
        if observed == self._observable_owned_file(handle.prior_owned_files[0]):
            return "prior"
        if observed == self._observable_owned_file(handle.target_owned_files[0]):
            return "target"
        return "other"

    def rollback_reconcile(self, handle, prior_desired):
        del prior_desired
        self.calls.append("rollback")
        return self._restore_exact_prior_owned_files(handle)


class LiveReferenceAdapter(FakeAdapter):
    """Reports the owned file's LIVE ownership row, not the receipt's copy.

    The distinction is the point of the archive tests: a handle built from the
    receipt would carry a stale archive reference, so rollback would restore
    whatever was recorded rather than what is actually on disk now.
    """

    def __init__(self, entry, env) -> None:
        super().__init__("claude", harness_result("claude", owned_entries=(entry,)))
        self._env = env

    def prepare_reconcile(self, receipt, prior_desired, desired):
        handle = super().prepare_reconcile(receipt, prior_desired, desired)
        _prior, current, errors = owned_file_ownership(
            receipt.owned_entries[0], env=self._env
        )
        assert not errors and current is not None
        return replace(handle, prior_owned_files=(current,))
