"""Shared fixtures for installed observer acceptance scenarios."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.observer_runtime as runtime
from manifest_agent.catalog import load_catalog
from manifest_agent.checks import toolchain_materialize as materializer
from manifest_agent.checks.toolchain_provision import provision
from manifest_agent.contracts import load_domain_contracts
from manifest_agent.models import (
    DesiredState,
    HarnessReceipt,
    InstallationReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
)
from manifest_agent.observer_runtime_identity import (
    bundle_tree_sha256,
    canonical,
    digest,
    generation_paths,
    observer_key_path,
    runtime_roots,
)
from manifest_agent.release import REPOSITORY_URL
from manifest_agent.service_state import bundle_checksums, with_source_fingerprints
from manifest_agent.state import installation_lock, write_receipt_atomic
from tests.python.manifest_agent._observer_locked_cache import offline_materializer_run
from tests.python.manifest_agent.test_build_manifest_release import _clean_fixture
from tools.build_manifest_release import build_release

__all__ = [
    "HARNESSES",
    "ROOT",
    "Path",
    "bundle_tree_sha256",
    "canonical",
    "digest",
    "generation_paths",
    "installation_lock",
    "installed_observer",
    "inventory",
    "isolated_public_command",
    "isolated_transaction",
    "json",
    "materializer",
    "observer_key_path",
    "os",
    "provision",
    "pytest",
    "replace",
    "runtime",
    "runtime_roots",
    "select",
    "subprocess",
    "sys",
    "tarfile",
    "with_source_fingerprints",
    "write_receipt_atomic",
]

ROOT = Path(__file__).resolve().parents[3]
HARNESSES = ("claude", "cursor", "codex", "devin", "antigravity", "omp")


def inventory(root):
    return {
        str(p.relative_to(root)): (
            p.lstat().st_mode,
            str(p.readlink())
            if p.is_symlink()
            else p.read_bytes()
            if p.is_file()
            else None,
        )
        for p in root.rglob("*")
    }


def isolated_public_command(arguments, fixture):
    """Deny checkout reads and network at the actual process boundary."""
    import shutil

    denied = (ROOT, fixture["base"] / "unavailable-source")
    if sys.platform == "darwin":
        sandbox = Path("/usr/bin/sandbox-exec")
        assert sandbox.is_file(), "installed acceptance requires OS sandbox"
        rules = " ".join(
            f"(deny file-read* (subpath {json.dumps(str(path))}))" for path in denied
        )
        return [
            str(sandbox),
            "-p",
            f"(version 1) (allow default) (deny network*) {rules}",
            *arguments,
        ]
    sandbox = shutil.which("bwrap")
    assert sandbox, (
        "installed acceptance requires sandbox-exec or bubblewrap; no unsandboxed fallback"
    )
    return [
        sandbox,
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--bind",
        str(fixture["base"]),
        str(fixture["base"]),
        "--bind",
        str(Path.cwd()),
        str(Path.cwd()),
        "--unshare-net",
        *(item for path in denied for item in ("--tmpfs", str(path))),
        "--",
        *arguments,
    ]


@pytest.fixture(scope="module")
def installed_observer(tmp_path_factory):
    base = tmp_path_factory.mktemp("installed-observer").resolve()
    source, env, release, desired = _installed_release_state(base)
    receipt = base / "authority/selected.json"
    project = release / runtime.PROJECT
    lock = json.loads((project / "uv-toolchain.lock.json").read_bytes())
    pin = lock["tools"]["uv"]["platforms"][runtime.platform_id()]
    supplied = os.environ["MANIFEST_TEST_UV_ARCHIVE"]
    uv_archive = Path(supplied).read_bytes()
    assert digest(uv_archive) == pin["sha256"], (
        "UV fixture must match the exact release pin"
    )
    archive_path = base / "locked-uv.archive"
    archive_path.write_bytes(uv_archive)

    def locked_fetch(url):
        assert url == pin["url"], (
            "observer attempted acquisition outside its projection lock"
        )
        return uv_archive

    def locked_provision(*args, **kwargs):
        return provision(*args, **kwargs, fetcher=locked_fetch)

    with pytest.MonkeyPatch.context() as patch:
        for name, value in env.items():
            patch.setenv(name, value)
        patch.setattr(runtime, "provision", locked_provision)
        patch.setattr(materializer, "_run", offline_materializer_run(materializer._run))
        with installation_lock(receipt.parent / "install.lock"):
            binding = runtime.prepare_observer_runtime(desired, receipt_path=receipt)
        provider = runtime._provider(project, binding.platform)
        environment, record = generation_paths(binding, provider, env)
        # An installed package must keep working with the original checkout gone.
        source.rename(base / "unavailable-source")
        yield {
            "base": base,
            "env": env,
            "desired": desired,
            "receipt": receipt,
            "binding": binding,
            "environment": environment,
            "record": record,
            "uv_archive": archive_path,
        }


def _installed_release_state(base):
    source = _clean_fixture(ROOT, base)
    built = build_release(source, base / "archive", "https://example.invalid/releases")
    env = {
        **os.environ,
        "HOME": str(base / "home"),
        "XDG_CACHE_HOME": str(base / "cache"),
        "XDG_DATA_HOME": str(base / "data"),
        "XDG_STATE_HOME": str(base / "state"),
        "XDG_CONFIG_HOME": str(base / "config"),
    }
    wheels = Path(os.environ["MANIFEST_TEST_OBSERVER_WHEELS"]).resolve(strict=True)
    assert wheels.is_dir() and tuple(wheels.glob("*.whl")), (
        "explicit locked-wheel fixture cache required"
    )
    env.update(UV_FIND_LINKS=str(wheels), UV_NO_INDEX="1", UV_OFFLINE="1")
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPYCACHEPREFIX",
    ):
        env.pop(name, None)
    cache = (
        base
        / "cache/manifest/releases"
        / f"{built.version}-{built.archive_sha256[:16]}"
    )
    cache.mkdir(parents=True)
    with tarfile.open(built.archive) as archive:
        archive.extractall(cache, filter="data")
    release = next(cache.iterdir())
    desired = with_source_fingerprints(
        DesiredState(
            built.version,
            built.commit,
            str(release),
            MarketplaceSource(
                MarketplaceSourceKind.GIT, REPOSITORY_URL + ".git", built.commit
            ),
            release,
            REPOSITORY_URL,
            False,
            built.archive_sha256,
            load_domain_contracts(release / "plugins"),
            frozenset(),
            HARNESSES,
            load_catalog(release / ".claude-plugin/marketplace.json"),
        )
    )
    return source, env, release, desired


def select(fixture, harness):
    desired = fixture["desired"]
    receipt = InstallationReceipt(
        1,
        "1",
        desired.release_version,
        desired.source_commit,
        False,
        desired.archive_sha256,
        bundle_checksums(desired),
        (),
        {
            harness: HarnessReceipt(
                harness,
                "1",
                "unavailable",
                (),
                (),
                {},
                False,
                ("native CLI intentionally absent",),
            )
        },
        None,
    )
    write_receipt_atomic(fixture["receipt"], receipt)
    return receipt


def isolated_transaction(fixture, root, monkeypatch):
    """Give one interruption an exclusive receipt and runtime XDG roots."""
    env = dict(fixture["env"])
    for key in ("XDG_DATA_HOME", "XDG_STATE_HOME"):
        path = root / key.lower()
        path.mkdir(parents=True)
        env[key] = str(path)
        monkeypatch.setenv(key, str(path))
    receipt = root / "authority" / "selected.json"
    select({**fixture, "receipt": receipt}, "claude")
    return env, receipt
