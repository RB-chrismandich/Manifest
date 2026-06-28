"""Step runners (one per interaction type) — US2 (T016).

Each runner takes an already-*resolved* step dict (``${state.*}``/``${env.*}``
substituted by the executor) plus the live handle it needs (a subprocess is
spawned for ``cli``; a Playwright ``APIRequestContext`` for ``api``; a ``Page``
for ``ui``) and returns a :class:`StepOutcome`.

Importing this package and its submodules must NOT require Playwright — the
runners receive their live handles from the executor, which is the only place
that imports ``playwright`` (lazily). That keeps ``cli``-only runs, and the bulk
of the test suite, dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CaptureError(RuntimeError):
    """A declared capture could not be extracted (step did not produce it)."""


@dataclass
class StepOutcome:
    """Transient result of running one step, before it becomes a StepResult."""

    passed: bool
    message: str = ""
    captures: dict[str, Any] = field(default_factory=dict)


def join_url(base: str | None, path: str) -> str:
    """Join a catalog/CLI base URL with a step path; absolute paths pass through."""
    if path.startswith(("http://", "https://")):
        return path
    if not base:
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")
