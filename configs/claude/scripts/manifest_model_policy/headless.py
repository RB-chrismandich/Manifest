"""Synchronous, single-provider headless CLI execution."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .skill_execution import _read_bounded_output, build_provider_invocation
from .skill_process import CommandRunner

_DEFAULT_PROVIDER_ORDER = (
    "antigravity",
    "cursor",
    "gemini",
    "codex",
    "claude",
    "devin",
)
_TIER_EQUIVALENTS = {
    "mini": ("haiku",),
    "haiku": ("mini",),
    "flash": ("sonnet",),
    "sonnet": ("flash",),
    "advanced": ("opus", "pro"),
    "opus": ("advanced", "pro"),
    "pro": ("advanced", "opus"),
}


@dataclass(frozen=True)
class CliRoute:
    """A selected CLI provider and its optional binary override."""

    provider: str
    binary_override: str | None = None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _on_path(binary: str) -> bool:
    if not binary:
        return False
    if os.path.isabs(binary) or binary.startswith("."):
        return os.path.isfile(binary) and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None


def _provider_from_binary(config: Mapping[str, Any], binary: str) -> str | None:
    name = Path(binary).name
    for provider, spec in _mapping(config.get("cli_agents")).items():
        configured = _mapping(spec).get("binary")
        if configured in (binary, name):
            return str(provider)
    return None


def _providers(config: Mapping[str, Any]) -> tuple[str, ...]:
    configured = config.get("provider_order")
    if isinstance(configured, list) and configured:
        return tuple(str(provider) for provider in configured)
    agents = _mapping(config.get("cli_agents"))
    return tuple(str(provider) for provider in agents) or _DEFAULT_PROVIDER_ORDER


def resolve_cli_route(
    config: Mapping[str, Any],
    *,
    section: str = "cddl_invoke",
    env_prefix: str = "CDDL_INVOKE",
) -> CliRoute | None:
    """Choose an installed CLI without an SDK or coordinator dependency."""
    settings = _mapping(config.get(section))
    provider = (
        os.environ.get(f"{env_prefix}_PROVIDER") or settings.get("provider") or "auto"
    )
    override = os.environ.get(f"{env_prefix}_CLI") or None
    if provider == "auto" and override:
        provider = _provider_from_binary(config, override) or "auto"
    candidates = (str(provider),) if provider != "auto" else _providers(config)
    agents = _mapping(config.get("cli_agents"))
    for candidate in candidates:
        spec = _mapping(agents.get(candidate))
        binary = override if provider != "auto" and override else spec.get("binary")
        if isinstance(binary, str) and _on_path(binary):
            return CliRoute(
                candidate, override if provider != "auto" and override else None
            )
    return None


def resolve_role_model_tier(charter_path: str | os.PathLike[str]) -> str:
    """Read the optional CDDL frontmatter tier, defaulting to sonnet."""
    try:
        text = Path(charter_path).expanduser().read_text(encoding="utf-8")
    except OSError:
        return "sonnet"
    if not text.startswith("---"):
        return "sonnet"
    end = text.find("\n---", 3)
    if end < 0:
        return "sonnet"
    for line in text[3:end].splitlines():
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip() or "sonnet"
    return "sonnet"


def resolve_provider_model(
    config: Mapping[str, Any], provider: str, tier: str
) -> str | None:
    """Resolve a role tier through the provider's policy mapping."""
    if tier == "auto":
        return None
    models = _mapping(_mapping(config.get("model_tiers")).get(provider))
    resolved = models.get(tier)
    if isinstance(resolved, str) and resolved:
        return resolved
    for alias in _TIER_EQUIVALENTS.get(tier, ()):
        resolved = models.get(alias)
        if isinstance(resolved, str) and resolved:
            return resolved
    return tier


def run_headless_prompt(
    route: CliRoute,
    prompt: str,
    config: Mapping[str, Any],
    *,
    model_tier: str = "sonnet",
    timeout: float | None = None,
    runner: CommandRunner | None = None,
) -> str:
    """Run one bounded prompt, raising for timeout, malformed output, or failure."""
    agents = _mapping(config.get("cli_agents"))
    configured = _mapping(agents.get(route.provider))
    if not configured:
        raise RuntimeError(f"no CLI configuration for {route.provider}")
    agent = dict(configured)
    if route.binary_override:
        agent["binary"] = route.binary_override
    timeout_value = timeout
    if timeout_value is None:
        timeout_value = _mapping(config.get("timeouts")).get("default", 120)
    model = resolve_provider_model(config, route.provider, model_tier)
    with tempfile.TemporaryDirectory(prefix="manifest-headless-") as temporary:
        root = Path(temporary)
        argv, stdin_bytes = build_provider_invocation(
            agent, model, prompt, root / "last-message.txt", root / "prompt.txt"
        )
        result = (runner or CommandRunner(float(timeout_value))).run(
            argv, stdin_bytes=stdin_bytes
        )
        if result.timed_out:
            raise TimeoutError(f"{argv[0]} timed out after {timeout_value}s")
        output, file_truncated = result.stdout, False
        output_file = root / "last-message.txt"
        if output_file.exists():
            output, file_truncated = _read_bounded_output(output_file)
            if not output:
                output = result.stdout
        if result.returncode != 0:
            raise RuntimeError(
                f"{route.provider} failed with exit status {result.returncode}"
            )
        if result.truncated or file_truncated:
            raise RuntimeError(f"{argv[0]} output exceeded the provider output limit")
        if not output.strip():
            raise RuntimeError(f"{argv[0]} returned empty output")
        return output
