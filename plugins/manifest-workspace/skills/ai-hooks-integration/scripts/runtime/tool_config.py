"""Centralized tool configuration for AI hooks integration.

This module provides a single source of truth for tool-specific configuration,
avoiding duplication across merge_hooks.py, remove_hooks.py, and other scripts.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import TypedDict


class ToolConfig(TypedDict, total=False):
    """Configuration for a single tool."""

    hook_key: str  # Key in hooks object (e.g., "PreToolUse")
    default_matcher: str | None  # Default matcher pattern
    nested: bool  # True = hooks[].hooks[], False = hooks[].command
    version: int  # Config version (Cursor only)
    config_path: str  # Default config file path
    plugin_template: str  # OpenCode only


# Centralized tool configuration
TOOL_CONFIG: dict[str, ToolConfig] = {
    "claude": {
        "hook_key": "PreToolUse",
        "default_matcher": "Bash",
        "nested": True,
        "config_path": "~/.claude/settings.json",
    },
    "gemini": {
        "hook_key": "BeforeTool",
        "default_matcher": "run_shell_command",
        "nested": True,
        "config_path": "~/.gemini/settings.json",
    },
    "cursor": {
        "hook_key": "beforeShellExecution",
        "default_matcher": None,
        "nested": False,
        "version": 1,
        "config_path": "~/.cursor/hooks.json",
    },
    "opencode": {
        "plugin_template": "opencode_plugin",
        "config_path": "~/.config/opencode/plugins",
    },
}

# Tools that support JSON-based hooks (not OpenCode)
JSON_TOOLS = ["claude", "gemini", "cursor"]


def hook_support(tool: str, event: str) -> dict[str, object]:
    """Return a structured support result for a harness hook event."""
    config = TOOL_CONFIG.get(tool)
    if config is None or tool == "opencode":
        return {
            "event": event,
            "reason": f"{tool} has no JSON-native Manifest hook target",
            "status": "degraded",
            "supported": False,
            "tool": tool,
        }
    supported = event == config.get("hook_key")
    return {
        "event": event,
        "reason": None if supported else f"{event} is not native to {tool}",
        "status": "native" if supported else "degraded",
        "supported": supported,
        "tool": tool,
    }


def get_config(tool: str) -> ToolConfig:
    """Get configuration for a tool.

    Args:
        tool: Tool name (claude, gemini, cursor, opencode).

    Returns:
        Tool configuration dict.

    Raises:
        KeyError: If tool is not supported.
    """
    if tool not in TOOL_CONFIG:
        raise KeyError(f"Unknown tool: {tool}. Supported: {list(TOOL_CONFIG.keys())}")
    return TOOL_CONFIG[tool]


def get_default_path(tool: str) -> Path:
    """Get default config path for a tool.

    Args:
        tool: Tool name.

    Returns:
        Expanded Path to config file/directory.
    """
    cfg = get_config(tool)
    return Path(cfg.get("config_path", "")).expanduser()


def is_nested(tool: str) -> bool:
    """Check if tool uses nested hook structure.

    Args:
        tool: Tool name.

    Returns:
        True if hooks use nested structure (hooks[].hooks[]).
    """
    return get_config(tool).get("nested", False)


class ConfigUnreadable(Exception):
    """An existing config file could not be understood, so it must not be rewritten.

    Distinct from "file absent". Callers read a config, add their hook, and write
    the merged result back — so a load that reports "empty" for a file that is
    actually present-but-unparseable makes the caller write a file containing
    ONLY its own hook, destroying every unrelated setting. Raising instead forces
    the caller to abort with the file intact.
    """


# JSON utilities
def load_json(path: Path) -> dict:
    """Load a JSON object from `path`.

    Returns {} ONLY when the file does not exist — a legitimate "nothing to
    merge with, create it". Every other failure raises ConfigUnreadable, because
    the difference between absent and unreadable is the difference between
    creating a file and silently truncating one.
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ConfigUnreadable(f"cannot read {path}: {exc}") from exc
    if not raw.strip():
        # An empty file is unambiguous: nothing to preserve, safe to populate.
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigUnreadable(
            f"{path} is not valid JSON ({exc}). Refusing to overwrite it — "
            f"fix or move the file, then re-run. Nothing was changed."
        ) from exc
    if not isinstance(parsed, dict):
        # Previously returned {} with no warning at all, which was the quietest
        # path to data loss in this module.
        raise ConfigUnreadable(
            f"{path} contains a JSON {type(parsed).__name__}, not an object. "
            f"Refusing to overwrite it. Nothing was changed."
        )
    return parsed


def _current_umask() -> int:
    """The process umask, read without leaving it changed.

    os.umask only reports by setting, so the value has to be put back. New
    configs then land at the mode an ordinary `open()` would have produced,
    rather than mkstemp's private 0600.
    """
    mask = os.umask(0o022)
    os.umask(mask)
    return mask


def save_json(path: Path, data: dict, dry_run: bool = False) -> None:
    """Write `data` to `path` atomically, keeping a backup of any prior content.

    Two properties the previous bare `write_text` lacked:

    * Atomic — the payload lands in a same-directory temp file and is moved into
      place with os.replace(), so an interrupted write (or a crash mid-write)
      leaves the original file, not a truncated one. The temp file MUST share the
      directory: os.replace is only atomic within a filesystem.
    * Recoverable — existing content is copied to a sibling .bak first, so even a
      logic error upstream is undoable.

    Symlinks are resolved before writing so a symlinked config (a common dotfile
    layout) is updated at its real location instead of being replaced by a
    regular file.

    The prior mode is carried onto the replacement. os.replace swaps inodes, so
    without this the file inherits mkstemp's 0600 and a 0644 config silently
    became owner-only — while the copy2 backup kept 0644, leaving the BACKUP
    more permissive than the live file. Adding a hook must not change who can
    read a config.
    """
    if dry_run:
        print(f"[dry-run] write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.resolve() if path.is_symlink() else path
    existed = target.exists()
    if existed:
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
        if existed:
            shutil.copymode(target, tmp)
        else:
            os.chmod(tmp, 0o666 & ~_current_umask())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def has_hook(hooks: list, nested: bool, command: str) -> bool:
    """Check if a hook with the given command already exists.

    Args:
        hooks: List of hook entries.
        nested: Whether hooks use nested structure.
        command: Command string to search for (partial match).

    Returns:
        True if command is found in any hook entry.
    """
    if not isinstance(hooks, list):
        return False
    for h in hooks:
        if nested:
            inner = h.get("hooks", []) if isinstance(h, dict) else []
            for ih in inner:
                cmd = ih.get("command", "") if isinstance(ih, dict) else ""
                if command in cmd:
                    return True
        else:
            cmd = h.get("command", "") if isinstance(h, dict) else ""
            if command in cmd:
                return True
    return False
