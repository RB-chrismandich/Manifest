""".pth validation for the python-env distribution-set digest.

Python executes import lines in `.pth` files during startup.  A path line may
only name a location inside the materialized environment.  Accepted files are
hashed byte-for-byte: no checkout path is a trust input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvTrust:
    """Explicit trusted context for environment verification."""

    store: Path
    repo_root: Path


# setuptools' own namespace-package `.pth` shim (the `<dist>-<version>-
# <pyver>-nspkg.pth` shape, e.g. `google_generativeai-0.8.6-py3.13-nspkg.pth`
# for this repo's `google-generativeai` dependency) -- a fixed, well-known
# template with only the namespace tuple substituted, generated identically
# by every setuptools release for every namespace package on PyPI. Its
# bytes name no checkout or store path at all (only `sitedir`, resolved at
# IMPORT time from `sys._getframe`), so unlike an arbitrary `import` line it
# is already checkout/store-independent -- trusted verbatim, never rejected
# as an untrusted `import` hook, PROVIDED it matches this pattern exactly
# (anchored start/end; any deviation falls through to the ordinary
# plain-path check below and is rejected).
_NAMESPACE_PACKAGE_PTH = re.compile(
    r"^import sys, types, os;"
    r"p = os\.path\.join\(sys\._getframe\(1\)\.f_locals\['sitedir'\], \*\((?:'[^']+', ?)+\)\);"
    r"importlib = __import__\('importlib\.util'\);__import__\('importlib\.machinery'\);"
    r"m = sys\.modules\.setdefault\('(?P<name>[^']+)', importlib\.util\.module_from_spec\("
    r"importlib\.machinery\.PathFinder\.find_spec\('(?P=name)', \[os\.path\.dirname\(p\)\]\)\)\);"
    r"m = m or sys\.modules\.setdefault\('(?P=name)', types\.ModuleType\('(?P=name)'\)\);"
    r"mp = \(m or \[\]\) and m\.__dict__\.setdefault\('__path__',\[\]\);\(p not in mp\) and mp\.append\(p\)$"
)


class UntrustedPthError(ValueError):
    """A `.pth` file can execute code or redirect imports outside its env."""


def _contained_pth_path(line: str, pth_path: Path, env_root: Path) -> None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return
    if stripped.startswith("import "):
        raise UntrustedPthError(f"untrusted .pth line: {stripped!r}")
    candidate = Path(stripped)
    target = candidate if candidate.is_absolute() else pth_path.parent / candidate
    try:
        target.resolve(strict=False).relative_to(env_root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise UntrustedPthError(f"untrusted .pth line: {stripped!r}") from error


def canonical_pth_bytes(pth_path: Path, env_root: Path) -> bytes:
    """Validate a `.pth` file and return its exact, attested bytes."""
    text = pth_path.read_text(encoding="utf-8", errors="surrogateescape")
    if _NAMESPACE_PACKAGE_PTH.match(text.strip()):
        return text.encode("utf-8", "surrogateescape")
    for line in text.splitlines():
        _contained_pth_path(line, pth_path, env_root)
    return text.encode("utf-8", "surrogateescape")
