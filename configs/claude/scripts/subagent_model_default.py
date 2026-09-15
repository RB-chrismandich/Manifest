#!/usr/bin/env python3
"""Best-effort Agent model-default hook, never an authorization boundary.

Shipped --native-default-only mode emits diagnostics but never rewrites input.
The version-gated native environment default also covers Workflow and preserves
invocation/frontmatter precedence. Managed and CLI definitions cannot reliably
be discovered by this hook, so filesystem-based injection is not shipped.

Legacy direct invocation still fills omitted models after checking visible pins,
explicit environment choices and forks. It cannot guarantee hidden-pin coverage.
Errors fail open with redacted stderr diagnostics; requested is not served.

See docs/model-policy/dispatch-reliability.md for host gates and limitations.
"""

from __future__ import annotations

import glob
import json
import os
import sys

PROG = "subagent_model_default.py"

# The dispatch tool is `Agent`; `Task` is accepted because that was its previous
# name and a stale matcher must degrade to a no-op, never to a wrong rewrite.
DISPATCH_TOOLS = {"Agent", "Task"}

# `fork` inherits the parent model by design (see module docstring).
NO_MODEL_AGENTS = {"fork"}

DEFAULT_MODEL = "sonnet"


def err(*args: object) -> None:
    print(f"{PROG}:", *args, file=sys.stderr)


def usage() -> None:
    print(
        "Usage: subagent_model_default.py [--native-default-only] [--help]\n"
        "\n"
        "PreToolUse hook for the Agent tool. Reads a hook payload on stdin and,\n"
        "when the dispatch names no model, emits hookSpecificOutput.updatedInput\n"
        "injecting the default sub-agent model (SUBAGENT_DEFAULT_MODEL, default\n"
        "sonnet).\n"
        "\n"
        "Left alone: an explicit `model` on the call, an agent whose frontmatter\n"
        "sets `model:`, and `fork` (which ignores model by design).\n"
        "\n"
        "Shipped --native-default-only mode never injects; native host precedence\n"
        "preserves pins invisible to filesystem discovery. Errors exit 0 with\n"
        "redacted diagnostics on stderr. No change means no stdout."
    )


def installed_plugin_state(home: str) -> tuple[set[str], set[str]] | None:
    """(installed plugin names, installed cache paths), or None when unknown.

    `installed_plugins.json` records the exact `installPath` Claude Code loads,
    which is the only authority on WHICH version is live. Skipping
    `.orphaned_at` alone left two holes: marketplace roots carry no marker, so
    an uninstalled plugin resurrected its pin from there; and between two live
    versions the lexicographically-first won, handing an upgrade window to the
    OLDER pin.

    None means the record is absent or unreadable, and every caller must then
    fall back to scanning everything. A hook that honoured no pins at all
    because one JSON file went missing would be worse than the bug it fixes.
    """
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    path = os.path.join(config, "plugins", "installed_plugins.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return None
    names: set[str] = set()
    paths: set[str] = set()
    for key, entries in plugins.items():
        names.add(key.split("@", 1)[0])
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("installPath"):
                paths.add(os.path.normpath(str(entry["installPath"])))
    return names, paths


def agent_definition_roots() -> list[tuple[str, str]]:
    """(directory, owning plugin) pairs, narrowest scope first; "" = no plugin.

    The plugin name comes from the glob that MATCHED the directory, never from
    re-parsing the path afterwards. Deriving it by index cannot work: the two
    layouts put the name at different depths, and anchoring on a path segment
    equal to the literal ``plugins`` or ``cache`` lets a plugin whose own
    directory carries that name impersonate the marker and reintroduce the very
    off-by-one the anchor was added to remove.

    Orphaned versions are skipped. ``claude plugin uninstall`` leaves the tree
    in place with an ``.orphaned_at`` marker instead of deleting it, and glob
    order is filesystem order, so an uninstalled version could otherwise beat
    the live one and pin a model the user has already removed. Sorted so the
    resolution order is reproducible rather than whatever the OS listed first.
    """
    home = os.path.expanduser("~")
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    roots: list[tuple[str, str]] = []
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        roots.append((os.path.join(project, ".claude", "agents"), ""))
    roots.append((os.path.join(config, "agents"), ""))

    base = os.path.join(config, "plugins")
    state = installed_plugin_state(home)
    # marketplaces/<market>/plugins/<plugin>/agents
    for root in sorted(
        glob.glob(os.path.join(base, "marketplaces", "*", "plugins", "*", "agents"))
    ):
        name = os.path.basename(os.path.dirname(root))
        if state is not None and name not in state[0]:
            continue
        roots.append((root, name))
    # cache/<market>/<plugin>/<version>/agents
    for root in sorted(glob.glob(os.path.join(base, "cache", "*", "*", "*", "agents"))):
        version_dir = os.path.dirname(root)
        if os.path.exists(os.path.join(version_dir, ".orphaned_at")):
            continue
        if state is not None and os.path.normpath(version_dir) not in state[1]:
            continue
        roots.append((root, os.path.basename(os.path.dirname(version_dir))))
    return roots


def frontmatter(path: str) -> dict[str, str]:
    """Parse the leading `---` YAML block as flat key: value pairs.

    Deliberately a line scan rather than a yaml.safe_load: this runs on every
    dispatch, only two scalar keys matter, and a hook must not fail because a
    plugin shipped an agent file with a YAML quirk somewhere below the keys we
    read.
    """
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            if fh.readline().strip() != "---":
                return out
            for line in fh:
                if line.strip() == "---":
                    break
                key, sep, value = line.partition(":")
                if sep and not key.startswith((" ", "\t", "#")):
                    out[key.strip()] = value.strip().strip("\"'")
    except OSError:
        return {}
    return out


def declared_model(subagent_type: str) -> str | None:
    """The model an agent definition for ``subagent_type`` pins, else None.

    Matches on the frontmatter `name` and on the filename stem, each optionally
    plugin-qualified (``pr-review-toolkit:code-reviewer``). Ambiguity resolves
    CONSERVATIVELY: the first candidate that declares a model wins. A missed
    injection costs money; a wrong one silently overrides a deliberate choice,
    which is the failure this hook exists to avoid.

    Shared with subagent_breakdown.py --audit on purpose. If the hook and the
    audit disagreed about what counts as frontmatter-pinned, the audit would
    flag exactly the dispatches the hook deliberately skips.
    """
    if not subagent_type:
        return None
    wanted = subagent_type.strip()
    for root, plugin in agent_definition_roots():
        for path in sorted(glob.glob(os.path.join(root, "*.md"))):
            fm = frontmatter(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            name = fm.get("name", "")
            aliases = {stem, name}
            if plugin:
                aliases |= {f"{plugin}:{stem}", f"{plugin}:{name}"}
            if wanted in aliases and fm.get("model"):
                return fm["model"]
    return None


def declares_model(subagent_type: str) -> bool:
    """True when an agent definition for ``subagent_type`` pins its own model."""
    return declared_model(subagent_type) is not None


def decide(payload: dict) -> dict | None:
    """Return the hook output for ``payload``, or None to stay silent."""
    if payload.get("tool_name") not in DISPATCH_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        err("fail-open: missing or malformed tool_input")
        return None

    # Native defaults resolve all host scopes, including managed/CLI definitions.
    # An injected per-call model would override a deliberate process default.
    if any(
        key in os.environ
        for key in ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE")
    ):
        return None

    model = tool_input.get("model")
    if model is not None and not isinstance(model, str):
        err("fail-open: malformed model")
        return None
    if isinstance(model, str) and model.strip():
        return None  # explicit pin — precedence layer 1, leave it

    subagent_type = tool_input.get("subagent_type") or ""
    if not isinstance(subagent_type, str):
        return None
    if subagent_type.strip() in NO_MODEL_AGENTS:
        return None  # fork ignores model; injecting would poison the sidecar
    if declares_model(subagent_type):
        return None  # precedence layer 2 — the agent definition decided

    default = os.environ.get("SUBAGENT_DEFAULT_MODEL", DEFAULT_MODEL).strip()
    if not default:
        return None

    # Echo the whole input back, not just {"model": ...}. The contract describes
    # updatedInput as replacing tool input; sending the full object is correct
    # under both replace-wholesale and merge-fields readings, and cannot drop
    # the prompt.
    updated = dict(tool_input)
    updated["model"] = default
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated,
            "additionalContext": (
                f"sub-agent model defaulted to {default} (no model was specified); "
                "explicit pins and agent frontmatter are left alone"
            ),
        }
    }


def main(argv: list[str]) -> int:
    if any(arg in ("--help", "-h") for arg in argv):
        usage()
        return 0
    if "--native-default-only" in argv:
        # Filesystem scans cannot see managed or --agents definitions. The
        # shipped hook observes the native default without overriding any pin.
        if not os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL", "").strip():
            err("native default unobserved; worker model coverage is incomplete")
        if os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE"):
            err("native force override present; explicit worker pins may be overridden")
        return 0
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        err("fail-open: unreadable input")
        return 0
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        err("fail-open: malformed JSON")
        return 0
    if not isinstance(payload, dict):
        err("fail-open: expected object")
        return 0
    try:
        out = decide(payload)
    except Exception:
        # This cost optimization is not an authorization boundary. Fail open,
        # but never include exception text that could contain a private payload.
        err("fail-open: model default could not be resolved")
        return 0
    if out is not None:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
