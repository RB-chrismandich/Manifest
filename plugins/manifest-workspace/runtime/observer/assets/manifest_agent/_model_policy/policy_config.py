"""File-backed configuration for retained single-provider policy."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

_POLICY_ENV = "MANIFEST_MODEL_POLICY"
_CONFIG_DIR_ENV = "MANIFEST_CONFIG_DIR"
_ROSTER_ENV = "MANIFEST_AGENT_ROSTER"
_DEFAULT_CONFIG_DIR = Path("~/.claude/config")


def _expanded(value: str | Path) -> Path:
    return Path(value).expanduser()


def resolve_policy_path(path: str | Path | None = None) -> Path:
    """Resolve policy path: explicit, environment, configured directory, home."""
    if path is not None:
        return _expanded(path)
    configured = os.environ.get(_POLICY_ENV)
    if configured:
        return _expanded(configured)
    directory = os.environ.get(_CONFIG_DIR_ENV)
    if directory:
        return _expanded(directory) / "model_policy.yml"
    return _DEFAULT_CONFIG_DIR.expanduser() / "model_policy.yml"


def load_default_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Load a required model policy mapping from its resolved location."""
    resolved = resolve_policy_path(path)
    try:
        value = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"malformed model policy: {resolved}") from error
    if not isinstance(value, dict):
        raise ValueError("model policy config must be a mapping")
    return value


def _resolve_roster_path(path: str | Path | None) -> Path:
    if path is not None:
        return _expanded(path)
    configured = os.environ.get(_ROSTER_ENV)
    if configured:
        return _expanded(configured)
    directory = os.environ.get(_CONFIG_DIR_ENV)
    if directory:
        return _expanded(directory) / "agent_roster.yml"
    return _DEFAULT_CONFIG_DIR.expanduser() / "agent_roster.yml"


def load_agent_roster(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the optional agent roster, degrading safely to an empty mapping."""
    try:
        value = yaml.safe_load(_resolve_roster_path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(value, Mapping):
        return {}
    agents = value.get("agents")
    if not isinstance(agents, Mapping):
        return {}
    return {
        str(name): dict(spec)
        for name, spec in agents.items()
        if isinstance(spec, Mapping)
    }
