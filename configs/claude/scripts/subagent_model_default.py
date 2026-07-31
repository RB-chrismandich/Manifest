#!/usr/bin/env python3
"""subagent_model_default.py — PreToolUse hook: fill in an omitted sub-agent model.

A dispatch that names no model inherits the parent session's model, billing the
premium main-loop tier for fan-out work. Measured 2026-07-25 over the full
transcript corpus: pin compliance was 7.3% (168/2,307 dispatches), and $951.70
(56.3%) of all-time sub-agent spend was recoverable — essentially all of it from
*omitted* models, never from an explicit pin being overridden.

A natural-language rule ("pin Sonnet by default") was already loaded in every
session, including the ones that inherited. This hook is the mechanism that
prose could not be: it rewrites the tool arguments before the call runs.

WHAT IT DOES NOT TOUCH (each of these is a deliberate model choice, and
clobbering one would be a worse bug than the one being fixed):

  * an explicit ``model`` on the call — precedence layer 1, the caller decided;
  * an agent definition whose frontmatter sets ``model:`` — precedence layer 2.
    A call-site model OUTRANKS frontmatter, so injecting here would silently
    downgrade e.g. ``pr-review-toolkit:code-reviewer`` (``model: opus``) to
    Sonnet. MODEL-POLICY.md permits Opus for adversarial verification; this hook
    must not quietly revoke that permission.
  * ``fork``, which inherits the parent model by design and ignores ``model``
    entirely. Injecting there changes nothing real but records a *requested*
    model in the agent-<id>.meta.json sidecar that never served — poisoning the
    very audit (subagent_breakdown.py --audit) that verifies this hook works.

SCOPE. PreToolUse fires on the ``Agent`` tool, so this reaches Agent-tool
dispatches only. Workflow-tool agents (``agent()`` inside a Workflow script) do
not pass through it and remain governed by the script's own ``model`` option or
CLAUDE_CODE_SUBAGENT_MODEL. That is the largest single premium block measured
($919.32, workflow-subagent x Fable 5); the audit reports it separately rather
than letting this hook imply coverage it does not have.

Fail-open by construction: any error, any unparseable payload, any unexpected
shape prints nothing and exits 0, so a broken hook can never block a dispatch.

CLI:
    subagent_model_default.py            read hook payload on stdin
    subagent_model_default.py --help

Env overrides (tests): SUBAGENT_DEFAULT_MODEL (default "sonnet"),
CLAUDE_PROJECT_DIR / HOME for agent-definition discovery.
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
        "Usage: subagent_model_default.py [--help]\n"
        "\n"
        "PreToolUse hook for the Agent tool. Reads a hook payload on stdin and,\n"
        "when the dispatch names no model, emits hookSpecificOutput.updatedInput\n"
        "injecting the default sub-agent model (SUBAGENT_DEFAULT_MODEL, default\n"
        "sonnet).\n"
        "\n"
        "Left alone: an explicit `model` on the call, an agent whose frontmatter\n"
        "sets `model:`, and `fork` (which ignores model by design).\n"
        "\n"
        "Prints nothing and exits 0 on any error or when no change is needed."
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
    path = os.path.join(home, ".claude", "plugins", "installed_plugins.json")
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
    roots: list[tuple[str, str]] = []
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        roots.append((os.path.join(project, ".claude", "agents"), ""))
    roots.append((os.path.join(home, ".claude", "agents"), ""))

    base = os.path.join(home, ".claude", "plugins")
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
        return None

    model = tool_input.get("model")
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
    if argv and argv[0] in ("--help", "-h"):
        usage()
        return 0
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        out = decide(payload)
    except Exception as exc:
        if os.environ.get("SUBAGENT_MODEL_DEBUG") == "1":
            err(f"fail-open: {exc!r}")
        return 0
    if out is not None:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
