"""Scenario builders, fault injectors, and assertions for bootstrap-sync."""

import shutil
from dataclasses import replace
from pathlib import Path

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.codex_plugin_backup import (
    capture_owned_file_backup,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    CatalogPlugin,
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    ResultState,
)
from manifest_agent.ownership import owned_file_entry
from manifest_agent.service_state import bundle_checksums
from manifest_agent.state import read_receipt, write_receipt_atomic
from tests.python.manifest_agent._bootstrap_sync_fakes import (
    _RetirementCodexAdapter,
    _RetirementRunner,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
)


def _installed_row(path: Path) -> dict[str, object]:
    return {
        "pluginId": "manifest-workspace@manifest",
        "version": "0.1.0",
        "enabled": True,
        "source": {"path": str(path)},
    }


def _codex_receipt(prior, adapter) -> InstallationReceipt:
    """The prior-release receipt a retirement scenario starts from."""
    return InstallationReceipt(
        1,
        "1",
        prior.release_version,
        prior.source_commit,
        False,
        prior.archive_sha256,
        bundle_checksums(prior),
        (),
        {
            "codex": HarnessReceipt(
                "codex",
                adapter.adapter_version,
                "1.0.0",
                tuple(f"{plugin.name}@manifest" for plugin in prior.catalog_plugins),
                (),
                {},
                True,
            )
        },
    )


def _retirement_service(service_factory, tmp_path: Path):
    marketplace_root = tmp_path / "release"
    codex_home = tmp_path / "codex"
    cache_root = codex_home / "plugins/cache/manifest"
    for name in DOMAIN_BUNDLES:
        shutil.copytree(
            marketplace_root / "plugins" / name,
            cache_root / name / "1.0.0",
        )
    installed = cache_root / "manifest-retired/0.1.0"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("exact prior\n", encoding="utf-8")
    runner = _RetirementRunner(installed, marketplace_root)
    adapter = _RetirementCodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={
            "CODEX_HOME": str(codex_home),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
    )
    service = service_factory({"codex": adapter}, harnesses=("codex",))
    service.receipt_path = tmp_path / "state/manifest/installation.json"
    base, error = service._desired_state()
    assert error is None and base is not None
    prior = replace(
        base,
        catalog_plugins=(
            *base.catalog_plugins,
            CatalogPlugin("manifest-retired", "0.1.0", "./retired"),
        ),
    )
    desired = replace(
        base,
        release_version="2.0.0",
        source_commit="c" * 40,
        archive_sha256="d" * 64,
    )
    write_receipt_atomic(service.receipt_path, _codex_receipt(prior, adapter))

    def desired_state(selector=None, *, exact_release=False):
        if exact_release:
            assert selector == prior.release_version
            return prior, None
        return desired, None

    service._desired_state = desired_state
    journal = service.receipt_path.with_name(
        f".{service.receipt_path.name}.bootstrap-sync.json"
    )
    return service, adapter, runner, installed, desired, journal


def _addon_desired(service):
    desired, error = service._desired_state()
    assert error is None and desired is not None
    addon_path = desired.release_root / "plugins/manifest-i-have-adhd"
    addon_path.mkdir(parents=True, exist_ok=True)
    return replace(
        desired,
        catalog_plugins=(
            *desired.catalog_plugins,
            CatalogPlugin(
                "manifest-i-have-adhd", "0.1.0", "./plugins/manifest-i-have-adhd"
            ),
        ),
    )


def bump_release(service, version="2.0.0", commit="c" * 40, archive="d" * 64):
    """Point the service at a newer release, preserving the rest of the tuple.

    Every cross-harness test needs a release change to have something to
    converge; rebuilding the resolver inline made each one 11 lines longer and
    was the block C-DUPE kept flagging.
    """
    old_release = service.release_resolver(service.source)
    service.release_resolver = lambda selector: type(old_release)(
        version,
        commit,
        "v2",
        old_release.marketplace_source,
        old_release.release_root,
        old_release.repository_url,
        False,
        archive,
    )
    return old_release


def legacy_skill_home(tmp_path: Path, monkeypatch):
    """Build the pre-APM `~/.codex/skills` symlink layout and point HOME at it.

    Returns (home, legacy_symlink) so a caller can assert on either the tree or
    the link itself.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    legacy = home / ".codex/skills"
    legacy.symlink_to(source)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_SKILLS_DIR", str(source))
    return home, legacy


def owned_file_scenario(tmp_path: Path, installed_bytes: bytes):
    """A user-owned file plus its prior/installed archive rows.

    Both archive sagas need the same thing: a file that existed before Manifest
    touched it, an authenticated backup of that original, and a second backup of
    the release-installed content. Only the installed bytes differ between them.

    Returns (env, home, state_home, target, prior_row, installed_row,
    prior_backup, installed_backup).
    """
    home = tmp_path / "home"
    state_home = tmp_path / "state"
    env = {"HOME": str(home), "XDG_STATE_HOME": str(state_home)}
    target = home / ".config/example/owned.json"
    target.parent.mkdir(parents=True)

    target.write_bytes(b"user prior\n")
    prior_backup, prior_mode, prior_digest = capture_owned_file_backup(target, env)
    target.write_bytes(installed_bytes)
    installed_backup, installed_mode, installed_digest = capture_owned_file_backup(
        target, env
    )

    def row(mode, digest, backup):
        return {
            "path": str(target),
            "type": "file",
            "mode": mode,
            "digest": digest,
            "restore": {"archive": backup.to_dict()},
        }

    return (
        env,
        home,
        state_home,
        target,
        row(prior_mode, prior_digest, prior_backup),
        row(installed_mode, installed_digest, installed_backup),
        prior_backup,
        installed_backup,
    )


def journal_crash_after_removal(real_write):
    """A `_write_journal` wrapper that crashes once codex reports a removal.

    Reproduces the window this suite cares about: the plugin is gone from the
    native cache but the transaction has not been retired, so a restart must
    rebuild from the journal rather than from what it can observe.
    """

    def _write(path, saga):
        real_write(path, saga)
        codex = next(
            (item for item in saga.harness_mutations if item.harness == "codex"),
            None,
        )
        if codex is None:
            return
        handle = bootstrap_module._deserialize_handle(codex.handle)
        if any(item.retirement_phase == "removed" for item in handle.prior_inventory):
            assert codex.phase in {"applying", "applied"}
            raise SystemExit("injected post-removal crash")

    return _write


def journal_stop_at_codex_tombstone(real_write):
    """A `_write_journal` wrapper that stops the run once codex is tombstoned."""

    def _write(path, saga):
        real_write(path, saga)
        if any(
            item.harness == "codex" and item.phase == "tombstoned"
            for item in saga.harness_mutations
        ):
            raise RuntimeError("stop after durable restart tombstone")

    return _write


def stub_codex_convergence(adapter) -> None:
    """Make the adapter report a clean converged codex for a follow-up run."""
    adapter.install_capabilities = lambda selected: HarnessResult(
        "codex", ResultState.READY, (), {}
    )
    adapter.inspect = lambda selected: HarnessResult(
        "codex",
        ResultState.READY,
        tuple(f"{plugin.name}@manifest" for plugin in selected.catalog_plugins),
        {},
    )
    adapter.probe_adhd_hook = lambda selected: HarnessResult(
        "codex", ResultState.READY, (), {}
    )


def record_prepared_handles(adapter) -> list:
    """Capture every handle `prepare_reconcile` returns, for count assertions."""
    prepared: list = []
    real_prepare = adapter.prepare_reconcile

    def _record(*args, **kwargs):
        handle = real_prepare(*args, **kwargs)
        prepared.append(handle)
        return handle

    adapter.prepare_reconcile = _record
    return prepared


def three_harness_service(service_factory):
    """An installed service with claude, gemini and codex all participating."""
    claude = FakeAdapter("claude", harness_result("claude"))
    gemini = FakeAdapter("gemini", harness_result("gemini"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory(
        {"claude": claude, "gemini": gemini, "codex": codex},
        harnesses=("claude", "gemini", "codex"),
    )
    assert service.install().state is ResultState.READY
    return service, claude, gemini, codex


class ReleasePin:
    """Resolve the prior release by name and everything else to a live target.

    Compensation tests need both versions reachable at once: the transaction is
    mid-flight against a new target while rollback must still reconstruct the
    old one exactly. `target` is reassignable so a test can retarget mid-run —
    the original did this by rebinding a closed-over local, which worked but was
    invisible at the call site.
    """

    def __init__(self, service, previous_version: str) -> None:
        self.old_release = service.release_resolver(service.source)
        self._previous_version = previous_version
        self.target = self.release("2.0.0", "c" * 40, "d" * 64)
        service.release_resolver = self._resolve

    def release(self, version: str, commit: str, digest: str):
        """Build a release tuple that differs only in version/commit/digest."""
        old = self.old_release
        return type(old)(
            version,
            commit,
            version,
            old.marketplace_source,
            old.release_root,
            old.repository_url,
            False,
            digest,
        )

    def _resolve(self, selector):
        if selector == self._previous_version:
            return self.old_release
        return self.target


def fail_receipt_directory_fsync(monkeypatch, state_module, service):
    """Fail the receipt directory's fsync once, AFTER the rename succeeded.

    That is the only window where the new receipt is visible to a reader but not
    yet durable, which is what the restart path has to reason about.

    Returns a callable that puts the real implementations back, so the same
    test can drive the successful restart afterwards.
    """
    real_fsync = state_module._fsync_directory
    real_replace = state_module.os.replace
    seen = {"renamed": False, "failed": False}

    def record_replace(source_path, destination_path) -> None:
        real_replace(source_path, destination_path)
        if Path(destination_path) == service.receipt_path:
            seen["renamed"] = True

    def failing_fsync(path: Path) -> None:
        if (
            path == service.receipt_path.parent
            and seen["renamed"]
            and not seen["failed"]
        ):
            seen["failed"] = True
            raise OSError("injected receipt directory fsync failure")
        real_fsync(path)

    monkeypatch.setattr(state_module.os, "replace", record_replace)
    monkeypatch.setattr(state_module, "_fsync_directory", failing_fsync)

    def restore() -> None:
        monkeypatch.setattr(state_module, "_fsync_directory", real_fsync)
        monkeypatch.setattr(state_module.os, "replace", real_replace)

    return restore


def _claude_codex_receipt(prior_desired, entry) -> InstallationReceipt:
    """Prior receipt where claude owns one file and codex owns none."""
    return InstallationReceipt(
        1,
        "1",
        prior_desired.release_version,
        prior_desired.source_commit,
        False,
        prior_desired.archive_sha256,
        bundle_checksums(prior_desired),
        (),
        {
            "claude": HarnessReceipt(
                "claude", "1", "1.0.0", DOMAIN_BUNDLES, (entry,), {}, True
            ),
            "codex": HarnessReceipt(
                "codex", "1", "1.0.0", DOMAIN_BUNDLES, (), {}, True
            ),
        },
    )


def owned_file_saga_service(
    service_factory, state_home, target, prior, installed, claude
):
    """A claude+codex service whose receipt already owns `target`.

    Builds the prior receipt (with an authenticated owned-file entry), pins a
    newer desired release, and installs a `_desired_state` that answers both by
    name and by default — the shape every archive saga starts from.

    Returns (service, codex, desired, prior_desired, authoritative_prior).
    """
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory(
        {"claude": claude, "codex": codex}, harnesses=("claude", "codex")
    )
    service.receipt_path = state_home / "manifest/installation.json"
    prior_desired, error = service._desired_state()
    assert error is None and prior_desired is not None
    desired = replace(
        prior_desired,
        release_version="2.0.0",
        source_commit="c" * 40,
        archive_sha256="d" * 64,
    )
    entry = owned_file_entry(
        "example-owned-file",
        target,
        prior,
        installed,
        key_path=service.receipt_path.parent / "ownership.key",
    )
    write_receipt_atomic(
        service.receipt_path, _claude_codex_receipt(prior_desired, entry)
    )
    authoritative_prior = read_receipt(service.receipt_path)
    assert authoritative_prior is not None

    def desired_state(selector=None, *, exact_release=False):
        if exact_release:
            assert selector == prior_desired.release_version
            return prior_desired, None
        return desired, None

    service._desired_state = desired_state
    return service, codex, desired, prior_desired, authoritative_prior


def recording_journal_writer(monkeypatch):
    """Patch `_write_journal` to also collect every saga it persists."""
    recorded: list = []
    real_write = bootstrap_module._write_journal

    def _write(path, saga):
        real_write(path, saga)
        recorded.append(saga)

    monkeypatch.setattr(bootstrap_module, "_write_journal", _write)
    return recorded


def link_legacy_skills(home: Path, monkeypatch) -> None:
    """Point HOME at an existing tree carrying the pre-APM skills symlink."""
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex/skills").symlink_to(source)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_SKILLS_DIR", str(source))


def retire_owned_entry(service, persisted):
    """Drop the owned-file entry from the receipt and re-read it durably."""
    retired_claude = replace(
        persisted.harnesses["claude"],
        owned_entries=tuple(
            item
            for item in persisted.harnesses["claude"].owned_entries
            if item.identifier != "example-owned-file"
        ),
    )
    write_receipt_atomic(
        service.receipt_path,
        replace(persisted, harnesses={**persisted.harnesses, "claude": retired_claude}),
    )
    durable = read_receipt(service.receipt_path)
    assert durable is not None
    assert all(
        item.identifier != "example-owned-file"
        for item in durable.harnesses["claude"].owned_entries
    )
    return durable
