#!/usr/bin/env python3
"""Merge Claude runtime settings; preserve choices and report effective state.

Invoked by bootstrap, never by an edit/prompt hook. Version detection is bounded
and makes no model request. The receipt contains hashes/status only, not settings.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from merge_mcp_defaults import load_object, write_private_json
from subagent_model_default import DEFAULT_MODEL

MODEL_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"
FORCE_ENV = "CLAUDE_CODE_SUBAGENT_MODEL_FORCE"
MIN_DEFAULT_VERSION = (2, 1, 251)


def host_version(value: str) -> str:
    """Read version once per merge, never start an authenticated session."""
    if value != "auto":
        return value if re.fullmatch(r"\d+\.\d+\.\d+", value) else "unknown"
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    match = re.fullmatch(r"(\d+\.\d+\.\d+) \(Claude Code\)\s*", result.stdout)
    return match[1] if result.returncode == 0 and match else "unknown"


def validate(settings: dict) -> None:
    """Reject malformed merge surfaces before any target mutation."""
    for key in ("hooks", "permissions", "env"):
        if key in settings and not isinstance(settings[key], dict):
            raise ValueError(f"{key} must be an object")
    for rules in settings.get("permissions", {}).values():
        # Other permission scalars are legitimate host settings; only lists merge.
        if isinstance(rules, list) and any(not isinstance(rule, str) for rule in rules):
            raise ValueError("permission rules must be strings")
    allow = settings.get("permissions", {}).get("allow", [])
    if not isinstance(allow, list):
        raise ValueError("permissions.allow must be an array")
    for entries in settings.get("hooks", {}).values():
        if not isinstance(entries, list):
            raise ValueError("hook event must be an array")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                raise ValueError("hook entry must contain a hooks array")
            if any(not isinstance(hook, dict) for hook in entry["hooks"]):
                raise ValueError("hook must be an object")


def merge_permissions(source: dict, target: dict) -> None:
    """Retain the existing legacy migration and order-stable allow-rule union."""
    retired = {
        "Bash(~/.claude/scripts/version_pin.sh:*)",
        "Bash(~/.claude/scripts/version_pin_hook.sh:*)",
    }
    permissions = target.setdefault("permissions", {})
    allow = [rule for rule in permissions.get("allow", []) if rule not in retired]
    for rule in source.get("permissions", {}).get("allow", []):
        if rule not in allow:
            allow.append(rule)
    permissions["allow"] = allow


def merge_hooks(source: dict, target: dict, directory: Path) -> None:
    """Resolve shipped commands at the target, preserving arbitrary user hooks."""
    hooks = target.setdefault("hooks", {})
    legacy_default_commands = {
        "~/.claude/scripts/subagent_model_default.py",
        str(directory / "scripts/subagent_model_default.py"),
        shlex.quote(str(directory / "scripts/subagent_model_default.py")),
    }
    for event, entries in hooks.items():
        retained = []
        for entry in entries:
            kept = [
                h
                for h in entry["hooks"]
                if not (
                    isinstance(h.get("command"), str)
                    and (
                        h["command"] == "~/.claude/scripts/version_pin_hook.sh"
                        or h["command"].endswith("/.claude/scripts/version_pin_hook.sh")
                        or (
                            event == "PreToolUse"
                            and entry.get("matcher") == "Agent"
                            and h["command"] in legacy_default_commands
                        )
                    )
                )
            ]
            if kept:
                retained.append({**entry, "hooks": kept})
        hooks[event] = retained
    for event, entries in source.get("hooks", {}).items():
        current = hooks.setdefault(event, [])
        for entry in entries:
            resolved = deepcopy(entry)
            for hook in resolved["hooks"]:
                command = hook.get("command", "")
                if isinstance(command, str) and command.startswith("~/.claude/"):
                    words = shlex.split(command)
                    words[0] = str(directory / words[0][len("~/.claude/") :])
                    hook["command"] = shlex.join(words)
            if resolved not in current:
                current.append(resolved)


def owns_default(target: dict, previous: dict) -> bool:
    """Ownership survives receipt preparation and process-override observations."""
    return (
        bool(
            previous.get("owned_default")
            or previous.get("worker_default") == "seeded"
            or (
                previous.get("status") == "prepared"
                and previous.get("previous_owned_default")
            )
        )
        and target.get("env", {}).get(MODEL_ENV) == DEFAULT_MODEL
    )


def seed_default(target: dict, version: str, previous: dict) -> str:
    """Apply only the documented non-forcing default on supporting hosts."""
    env = target.get("env", {})
    supported = (
        version != "unknown"
        and tuple(map(int, version.split("."))) >= MIN_DEFAULT_VERSION
    )
    if not supported and owns_default(target, previous):
        del env[MODEL_ENV]
        return "unsupported-host"
    if MODEL_ENV in os.environ or FORCE_ENV in os.environ:
        return "process-override"
    if MODEL_ENV in env or FORCE_ENV in env:
        return (
            "seeded"
            if owns_default(target, previous)
            and env.get(MODEL_ENV) == DEFAULT_MODEL
            and FORCE_ENV not in env
            else "user-preserved"
        )
    if not supported:
        return "unsupported-host"
    target.setdefault("env", {})[MODEL_ENV] = DEFAULT_MODEL
    return "seeded"


def merge_document(source: dict, target: dict, directory: Path) -> None:
    """Retain scalar user-wins semantics; env belongs to the versioned default."""
    merge_permissions(source, target)
    for key, value in source.items():
        if key not in {"hooks", "permissions", "env", "_comment"}:
            target.setdefault(key, deepcopy(value))
    merge_hooks(source, target, directory)


def build_receipt(
    source_path: Path, settings_bytes: bytes, version: str, state: str, owned: bool
) -> dict:
    """Prepare provenance without embedding config values or transcripts."""
    return {
        "schema_version": 1,
        "status": "prepared",
        "host_version": version,
        "worker_default": state,
        "default_model": DEFAULT_MODEL,
        "owned_default": owned,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "policy_sha256": hashlib.sha256(
            source_path.read_bytes()
            + Path(__file__).read_bytes()
            + Path(__file__).with_name("subagent_model_default.py").read_bytes()
        ).hexdigest(),
        "settings_sha256": hashlib.sha256(settings_bytes).hexdigest(),
        "deployed_at": datetime.now(UTC).isoformat(),
        "served_model": None,
        "runtime_verified": False,
    }


def validate_paths(target_path: Path) -> Path:
    """Reject symlink destinations before writing settings or ownership state."""
    if target_path.is_symlink():
        raise ValueError("refusing a symlink settings target")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = target_path.parent / "config/runtime_settings_merge.json"
    for path in (
        receipt_path,
        receipt_path.parent,
        target_path.parent / ".manifest-runtime.lock",
    ):
        if path.is_symlink():
            raise ValueError("refusing a symlink runtime state target")
    return receipt_path


def perform(source_path: Path, target_path: Path, version: str, rollback: bool) -> bool:
    """Merge atomically under a lock; rollback removes only an owned default."""
    receipt_path = validate_paths(target_path)
    with (target_path.parent / ".manifest-runtime.lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = load_object(source_path)
        before = target_path.read_bytes() if target_path.exists() else None
        target = load_object(target_path) if before is not None else {}
        validate(source)
        validate(target)
        previous = load_object(receipt_path) if receipt_path.exists() else {}
        before_owned = owns_default(target, previous)
        if rollback:
            state = "rollback-preserved"
            if owns_default(target, previous):
                del target["env"][MODEL_ENV]
                state = "rolled-back"
        else:
            merge_document(source, target, target_path.parent.absolute())
            state = seed_default(target, version, previous)
        changed = before is None or json.loads(before) != target
        if (target_path.read_bytes() if target_path.exists() else None) != before:
            raise ValueError("settings changed during merge; retry explicitly")
        settings_bytes = (
            (json.dumps(target, indent=2) + "\n").encode()
            if changed
            else target_path.read_bytes()
        )
        report = build_receipt(
            source_path,
            settings_bytes,
            version,
            state,
            state == "seeded" or owns_default(target, previous),
        )
        report["previous_owned_default"] = before_owned
        # Durable preparation preserves rollback ownership if the final receipt
        # fails. A prepared receipt never certifies a successful settings merge.
        write_private_json(receipt_path, report)
        if changed:
            write_private_json(target_path, target)
        report["status"] = "merged"
        write_private_json(receipt_path, report)
        print(
            f"worker default: {state}; host={version}; runtime serving remains unverified"
        )
        print(
            "Merged Manifest runtime settings"
            if changed
            else "settings.json already has Manifest runtime settings"
        )
        return changed


def main(argv: list[str]) -> int:
    """Expose a deterministic version override for isolated compatibility tests."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--host-version", default="auto")
    parser.add_argument("--rollback-default", action="store_true")
    args = parser.parse_args(argv)
    try:
        perform(
            args.source,
            args.target,
            host_version(args.host_version),
            args.rollback_default,
        )
    except (OSError, ValueError) as exc:
        # Avoid exposing config values or JSON excerpts in deployment diagnostics.
        print(
            f"merge_runtime_settings.py: merge incomplete ({type(exc).__name__}); target preserved unless settings were committed before receipt failure",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
