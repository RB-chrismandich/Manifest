#!/usr/bin/env python3
"""Auto-trigger handler for post-pr-review-monitor.

Reads a tool-lifecycle hook payload on stdin (Claude PostToolUse, Gemini
AfterTool, Cursor afterShellExecution — normalized by ai-hooks-integration's
unified handler) and, when it sees a SUCCESSFUL `gh pr create` / `glab mr create`
shell command, emits hook output that nudges the agent to run the
post-pr-review-monitor skill on the just-created PR.

Fail-open by design: any parse error, a non-matching command, or a failed
command prints nothing and exits 0, so the hook never blocks normal work.

Debug: set HOOK_DEBUG=1 to log decisions to stderr.
"""
import json
import os
import re
import sys

# Matches `gh pr create ...` and `glab mr create ...` anywhere in the command
# (covers `cd foo && gh pr create`, leading env vars, etc.).
PR_CREATE_RE = re.compile(r"\b(gh\s+pr\s+create|glab\s+mr\s+create)\b")


def debug(msg: str) -> None:
    if os.environ.get("HOOK_DEBUG"):
        print(f"[pr-create-trigger] {msg}", file=sys.stderr)


def extract_command(payload: dict) -> str:
    """Pull the shell command out of the various tool payload shapes."""
    ti = payload.get("tool_input") or payload.get("toolInput") or {}
    if isinstance(ti, dict):
        cmd = ti.get("command") or ti.get("cmd")
        if cmd:
            return str(cmd)
    # Cursor afterShellExecution / Gemini AfterTool fallbacks
    for key in ("command", "cmd"):
        if payload.get(key):
            return str(payload[key])
    return ""


def succeeded(payload: dict) -> bool:
    """Best-effort success check; default True when the tool gives no signal."""
    resp = payload.get("tool_response") or payload.get("toolResponse") or {}
    if isinstance(resp, dict):
        if resp.get("success") is False:
            return False
        if isinstance(resp.get("exit_code"), int) and resp["exit_code"] != 0:
            return False
    if isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0:
        return False
    # PostToolUse only fires after success; PostToolUseFailure is a separate event.
    return True


def main() -> int:
    raw = sys.stdin.read()
    if not isinstance(raw, str):
        debug("payload not string; no-op")
        return 0

    if not raw.strip():
        payload = {}
    else:
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                payload = {}
        except json.JSONDecodeError:
            debug("payload not JSON; no-op")
            return 0

    command = extract_command(payload)
    if not PR_CREATE_RE.search(command):
        debug(f"no PR-create command in: {command!r}")
        return 0
    if not succeeded(payload):
        debug("PR-create command did not succeed; no-op")
        return 0

    debug("PR-create detected — emitting trigger")
    context = (
        "A pull/merge request was just created. Run the "
        "`post-pr-review-monitor` skill on this new PR: monitor CI to green "
        "(diagnosing and fixing failures), address GitHub Copilot findings if "
        "Copilot reviewed, and tag @google-labs-jules (if not already tagged) "
        "then watch for and address its feedback. Auto-detect the PR for the "
        "current branch."
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": payload.get("hook_event_name", "PostToolUse"),
            "additionalContext": context,
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
