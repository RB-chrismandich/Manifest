"""Shared temporary-checkout setup for local bootstrap recovery tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import ResultState
from manifest_agent.release import resolve_release
from tests.python.manifest_agent.test_service_install import FakeAdapter, harness_result


def _local_git_checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout"
    (repo / "tools").mkdir(parents=True)
    for name in DOMAIN_BUNDLES:
        bundle = repo / "plugins" / name
        bundle.mkdir(parents=True)
        (bundle / "payload.txt").write_text(f"{name}\n", encoding="utf-8")
    (repo / "tools" / "generate_plugin_views.py").write_text(
        "import sys\nraise SystemExit(0 if '--check' in sys.argv else 2)\n",
        encoding="utf-8",
    )
    for cmd in (
        ("init",),
        ("config", "user.email", "manifest@example.invalid"),
        ("config", "user.name", "Manifest Test"),
        ("add", "."),
        ("commit", "-m", "initial"),
    ):
        subprocess.run(("git", "-C", str(repo), *cmd), check=True, capture_output=True)
    return repo


def _installed_local_service(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    repo = _local_git_checkout(tmp_path)
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.source = repo
    service.release_resolver = resolve_release
    assert service.install().state is ResultState.READY
    return service, repo, claude, codex
