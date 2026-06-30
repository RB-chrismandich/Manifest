"""Runtime utilities for AI hooks integration.

This module provides runtime utilities for detecting the actual source
of hook invocations and filtering noise events.
"""

from .detect_source import detect_parent_source, get_process_cmdline
from .tool_config import (
    JSON_TOOLS,
    TOOL_CONFIG,
    get_config,
    get_default_path,
    has_hook,
    is_nested,
    load_json,
    save_json,
)

__all__ = [
    "JSON_TOOLS",
    "TOOL_CONFIG",
    "detect_parent_source",
    "get_config",
    "get_default_path",
    "get_process_cmdline",
    "has_hook",
    "is_nested",
    "load_json",
    "save_json",
]
