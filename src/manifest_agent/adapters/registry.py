"""Deterministic lazy registry for supported harness adapters."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from manifest_agent.adapters.base import HarnessAdapter

_ADAPTER_TYPES = {
    "claude": ("manifest_agent.adapters.claude", "ClaudeAdapter"),
    "codex": ("manifest_agent.adapters.codex", "CodexAdapter"),
    "gemini": ("manifest_agent.adapters.gemini", "GeminiAdapter"),
    "cursor": ("manifest_agent.adapters.cursor", "CursorAdapter"),
    "antigravity": ("manifest_agent.adapters.antigravity", "AntigravityAdapter"),
    "devin": ("manifest_agent.adapters.devin", "DevinAdapter"),
}


class AdapterRegistry:
    """Resolve concrete adapters lazily without coupling adapter modules."""

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Return the stable service and reporting order."""
        return tuple(_ADAPTER_TYPES)

    @classmethod
    def create(cls, name: str, *args: Any, **kwargs: Any) -> HarnessAdapter:
        """Construct one registered adapter without importing its siblings."""
        try:
            module_name, type_name = _ADAPTER_TYPES[name]
        except KeyError as error:
            supported = ", ".join(cls.names())
            raise ValueError(
                f"unsupported harness {name!r}; expected one of {supported}"
            ) from error
        adapter_type = getattr(import_module(module_name), type_name)
        return adapter_type(*args, **kwargs)
