"""Session-scoped HOME isolation for the coordinator suite.

Several tests in this package shell out to real harness binaries (`cursor`,
`codex`, `gemini`). Those binaries write config, logs and conversation history
into ``$HOME``, so running the suite against a developer's real home mutated it:
a measured run touched ``~/.cursor/cli-config.json``, ``~/.codex/logs_2.sqlite``
and ``~/.gemini/antigravity-cli/history.jsonl``, and created 480 entries in a
scratch home.

The fixture is session-scoped rather than per-test on purpose. Most of those 480
entries are caches; rebuilding them once per test would cost far more than it
buys, and the suite was measured to behave identically against an empty home, so
one shared empty home per session is sufficient isolation.

Tests that need their own home still set it with the function-scoped
``monkeypatch`` fixture, which takes precedence over this one.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Point HOME at a scratch directory for the whole session."""
    home = tmp_path_factory.mktemp("session-home")
    patch = pytest.MonkeyPatch()
    # Build caches are shared by design and are not the pollution that matters;
    # redirecting them made a measured full run go from 212s to 396s because
    # every wheel was rebuilt. Pin them back to their real locations, resolved
    # before HOME moves, so only configuration and state are isolated.
    real_home = Path.home()
    cache_defaults = {
        "XDG_CACHE_HOME": real_home / ".cache",
        "UV_CACHE_DIR": real_home / ".cache" / "uv",
        "PIP_CACHE_DIR": real_home / ".cache" / "pip",
    }
    for name, default in cache_defaults.items():
        patch.setenv(name, os.environ.get(name) or str(default))
    patch.setenv("HOME", str(home))
    # Windows and some libraries consult USERPROFILE instead of HOME.
    patch.setenv("USERPROFILE", str(home))
    try:
        yield home
    finally:
        patch.undo()
