"""Guard: this suite must never write into the developer's real home.

Several tests build wheels and shell out to tooling that writes under ``$HOME``.
A measured run against a scratch home created 454 entries. Without the
session-scoped isolation in ``conftest.py`` those land in the real home instead.
"""

from __future__ import annotations

import os
from pathlib import Path


def test_home_is_isolated_from_the_real_home(tmp_path_factory) -> None:
    """HOME must point somewhere under pytest's temp root, not the real home."""
    home = Path(os.environ["HOME"]).resolve()
    pytest_root = Path(tmp_path_factory.getbasetemp()).resolve()

    assert home.is_relative_to(pytest_root), (
        f"HOME is {home}, outside pytest's temp root {pytest_root}; "
        "the session-scoped isolation in conftest.py is not active"
    )


def test_path_home_agrees_with_the_isolated_home() -> None:
    """Path.home() must follow HOME, since production code resolves through it."""
    assert Path.home().resolve() == Path(os.environ["HOME"]).resolve()


def test_shared_build_caches_are_not_redirected_into_the_temp_home() -> None:
    """Caches stay shared on purpose: isolating them rebuilt every wheel.

    Only configuration and state need isolating. Redirecting the caches too made
    a measured run of two build-heavy modules go from 141s to 154s and created
    449 extra entries per session.
    """
    home = Path(os.environ["HOME"]).resolve()
    for name in ("XDG_CACHE_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR"):
        value = os.environ.get(name)
        assert value, f"{name} should be pinned by the isolation fixture"
        assert not Path(value).resolve().is_relative_to(home), (
            f"{name}={value} points inside the temp home, so caches are rebuilt "
            "every session"
        )
