#!/usr/bin/env python3
"""Unified hook normalization for explicitly selected native harness targets.

Features:
- Configurable event filtering
- Debug logging (HOOK_DEBUG=1)
- Event normalization to canonical format

Usage:
  # Direct invocation (for testing)
  echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | \\
      python unified_hook.py --source claude

  # As a hook command
  python /path/to/unified_hook.py --handler /path/to/your_handler.py

Environment:
  HOOK_DEBUG=1      Enable debug logging to stderr
  HOOK_LOG_FILE     Log to file instead of stderr
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# No __pycache__ beside this skill: ~/.claude/skills is apm-owned and apm
# declines to adopt a directory holding files it did not place, so a cache dir
# here makes deploy silently skip the whole skill. The importing process — not
# the imported module — decides this, because by the time runtime/detect_source
# could set the flag its own .pyc is already on disk. Complements the `-B` this
# script's own spawn sites pass (install_all.py, run_handler below): those cover
# the hook path, this covers every other way the script gets run.
sys.dont_write_bytecode = True

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def debug_log(msg: str) -> None:
    """Log debug message if HOOK_DEBUG=1."""
    if os.environ.get("HOOK_DEBUG") != "1":
        return

    log_file = os.environ.get("HOOK_LOG_FILE")
    if log_file:
        with open(log_file, "a") as f:
            f.write(f"[unified_hook] {msg}\n")
    else:
        print(f"[unified_hook] {msg}", file=sys.stderr)


def extract_cwd(payload: dict) -> str:
    """Extract cwd from various payload formats.

    Different tools use different field names:
    - Claude: cwd
    - Gemini: working_directory
    - Cursor: cwd
    - OpenCode: cwd (in tool input)
    """
    # Direct cwd field
    if "cwd" in payload:
        return payload["cwd"]

    # Gemini uses working_directory
    if "working_directory" in payload:
        return payload["working_directory"]

    # Check tool_input for nested cwd
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict) and "cwd" in tool_input:
        return tool_input["cwd"]

    return ""


def extract_command(payload: dict) -> str:
    """Extract command from various payload formats."""
    # Claude/Gemini: tool_input.command
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command", "")
        if cmd:
            return cmd

    # Cursor: args.command
    args = payload.get("args", {})
    if isinstance(args, dict):
        cmd = args.get("command", "")
        if cmd:
            return cmd

    return ""


def should_drop_event(source: str, payload: dict) -> tuple[bool, str]:
    """Determine if an event should be dropped (filtered out).

    Args:
        source: The detected source tool.
        payload: The event payload.

    Returns:
        Tuple of (should_drop, reason).
    """
    # OpenCode events should be handled by its dedicated plugin
    # to avoid duplicate processing
    if source == "opencode":
        return True, "OpenCode events handled by dedicated plugin"

    return False, ""


def normalize_event(source: str, payload: dict, event_type: str = "PreToolUse") -> dict:
    """Normalize event to canonical format.

    Canonical format:
    {
        "event_type": "PreToolUse",
        "source": "claude",
        "session_id": "...",
        "cwd": "/path/to/project",
        "tool_name": "Bash",
        "tool_input": {...},
        "timestamp": "...",
        "raw_payload": {...}
    }
    """
    return {
        "event_type": event_type,
        "source": source,
        "session_id": payload.get("session_id", ""),
        "cwd": extract_cwd(payload),
        "tool_name": payload.get("tool_name", payload.get("tool", "")),
        "tool_input": payload.get("tool_input", payload.get("args", {})),
        "timestamp": payload.get("timestamp", ""),
        "raw_payload": payload,
    }


def allow_response(event_type: str = "PreToolUse", source: str = "claude") -> dict:
    """Generate an allow response in the selected harness's native shape."""
    if source == "gemini":
        return {"decision": "allow"}
    if source == "cursor":
        return {"permission": "allow", "continue": True}
    return {
        "hookSpecificOutput": {
            "hookEventName": event_type,
            "permissionDecision": "allow",
        },
        "continue": True,
    }


def deny_response(
    reason: str, event_type: str = "PreToolUse", source: str = "claude"
) -> dict:
    """Generate a blocking response in the selected harness's native shape."""
    if source == "gemini":
        return {"decision": "deny", "reason": reason}
    if source == "cursor":
        return {
            "permission": "deny",
            "continue": False,
            "user_message": reason,
            "agent_message": reason,
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": event_type,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "continue": False,
    }


def run_handler(handler_path: str, event: dict) -> dict:
    """Run external handler script and return its response.

    The handler receives normalized event JSON on stdin and should
    output a response JSON on stdout.
    """
    import subprocess

    try:
        result = subprocess.run(
            # -B: handlers live in apm-managed skill directories, and any
            # sibling module a handler imports would leave __pycache__ there —
            # a file apm did not place, which makes it refuse to update that
            # skill. See install_all.py for the same guard on the hook command.
            [sys.executable, "-B", handler_path],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            debug_log(f"Handler error: {result.stderr}")
            return {"decision": "allow"}

        raw_out = result.stdout
        if raw_out.strip():
            try:
                parsed = json.loads(raw_out)
                if isinstance(parsed, dict):
                    return parsed
                else:
                    print("Handler invalid JSON: not a JSON object", file=sys.stderr)
                    return {"decision": "allow"}
            except json.JSONDecodeError as e:
                print(f"Handler invalid JSON: {e}", file=sys.stderr)
                return {"decision": "allow"}
        return {"decision": "allow"}

    except subprocess.TimeoutExpired:
        debug_log("Handler timeout")
        return {"decision": "allow"}
    except json.JSONDecodeError as e:
        debug_log(f"Handler invalid JSON: {e}")
        print(f"Handler invalid JSON: {e}", file=sys.stderr)
        return {"decision": "allow"}
    except Exception as e:
        debug_log(f"Handler exception: {e}")
        print(f"Handler exception: {e}", file=sys.stderr)
        return {"decision": "allow"}


def adapt_handler_response(source: str, event_type: str, response: dict) -> dict:
    """Translate a canonical or native handler response to the target contract."""
    nested = response.get("hookSpecificOutput", {})
    if not isinstance(nested, dict):
        nested = {}
    decision = response.get("decision") or response.get("permission")
    decision = decision or nested.get("permissionDecision")
    denied = decision in {"deny", "block"} or response.get("continue") is False
    reason = response.get("reason") or response.get("user_message")
    reason = reason or nested.get("permissionDecisionReason") or "Blocked by hook"
    if denied:
        return deny_response(str(reason), event_type, source)
    return allow_response(event_type, source)


def main() -> None:
    ap = argparse.ArgumentParser(description="Unified hook with source detection")
    ap.add_argument(
        "--source",
        default="claude",
        choices=["claude", "gemini", "cursor", "opencode"],
        help="Native source tool selected by the installer",
    )
    ap.add_argument(
        "--event-type",
        default="PreToolUse",
        help="Event type for normalization",
    )
    ap.add_argument(
        "--handler",
        help="Path to handler script to process events",
    )
    ap.add_argument("--no-detect", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument(
        "--no-filter",
        action="store_true",
        help="Disable event filtering",
    )
    ap.add_argument(
        "--normalize-only",
        action="store_true",
        help="Output normalized event and exit (no handler)",
    )
    args = ap.parse_args()

    # Read payload from stdin
    raw_input = sys.stdin.read()
    payload = {}
    if not isinstance(raw_input, str):
        print("Invalid input: not a string", file=sys.stderr)
        print(json.dumps(allow_response(args.event_type, args.source)))
        return

    if raw_input.strip():
        try:
            payload = json.loads(raw_input)
            # The hook contract is a JSON *object*; anything else (array,
            # number, string) cannot be consumed by normalize_event's
            # payload.get(...) and must fail open like a parse error.
            if not isinstance(payload, dict):
                print("Invalid input JSON: not a JSON object", file=sys.stderr)
                print(json.dumps(allow_response(args.event_type, args.source)))
                return
        except json.JSONDecodeError as e:
            print(f"Invalid input JSON: {e}", file=sys.stderr)
            print(json.dumps(allow_response(args.event_type, args.source)))
            return

    debug_log(f"Received payload: {json.dumps(payload)[:200]}...")

    source = args.source
    debug_log(f"Effective source: {source}")

    # Event filtering
    if not args.no_filter:
        should_drop, reason = should_drop_event(source, payload)
        if should_drop:
            debug_log(f"Event dropped: {reason}")
            print(json.dumps(allow_response(args.event_type, args.source)))
            return

    # Normalize event
    event = normalize_event(source, payload, args.event_type)
    debug_log(f"Normalized event: {json.dumps(event)[:200]}...")

    # Output normalized event only
    if args.normalize_only:
        print(json.dumps(event, indent=2))
        return

    # Run handler if specified
    if args.handler:
        response = adapt_handler_response(
            source, args.event_type, run_handler(args.handler, event)
        )
    else:
        response = allow_response(args.event_type, source)

    print(json.dumps(response))


if __name__ == "__main__":
    main()
