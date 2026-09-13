"""Immutable data records for declarative project checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckSpec:
    id: str
    group: str
    category: str
    argv: tuple[str, ...]
    cwd: str
    inputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    timeout_seconds: float
    selection: str
    tool: str
    version: str
    honors_status_contract: bool = False


@dataclass(frozen=True)
class CheckResult:
    id: str
    status: str
    returncode: int | None
    duration_seconds: float
    diagnostics: str = ""
    selected_inputs: tuple[str, ...] = ()
    findings: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class Candidate:
    root: Path
    digest: str
    head_sha: str
    tree_sha: str
    base_sha: str = ""
