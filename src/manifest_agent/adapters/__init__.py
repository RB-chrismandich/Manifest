"""Public harness adapter contracts."""

from manifest_agent.adapters.base import (
    Detection,
    HarnessAdapter,
    combine_results,
    native_command_result,
    normalize_component_identity,
    run_native_command,
    verify_declared_components,
    verify_required_plugins,
)
from manifest_agent.adapters.registry import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "Detection",
    "HarnessAdapter",
    "combine_results",
    "native_command_result",
    "normalize_component_identity",
    "run_native_command",
    "verify_declared_components",
    "verify_required_plugins",
]
