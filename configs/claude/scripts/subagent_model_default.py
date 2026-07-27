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


def agent_definition_roots() -> list[str]:
    """Directories that can hold agent definitions, narrowest scope first."""
    home = os.path.expanduser("~")
    roots = []
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        roots.append(os.path.join(project, ".claude", "agents"))
    roots.append(os.path.join(home, ".claude", "agents"))
    # Plugin layouts: marketplaces/<market>/plugins/<plugin>/agents/<agent>.md
    #                 cache/<market>/<plugin>/<version>/agents/<agent>.md
    roots.extend(
        glob.glob(
            os.path.join(
                home,
                ".claude",
                "plugins",
                "marketplaces",
                "*",
                "plugins",
                "*",
                "agents",
            )
        )
    )
    roots.extend(
        glob.glob(
            os.path.join(home, ".claude", "plugins", "cache", "*", "*", "*", "agents")
        )
    )
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
    _, _, bare = wanted.rpartition(":")
    for root in agent_definition_roots():
        # Plugin name is the directory two or three levels up depending on layout;
        # comparing every alias below makes the exact layout irrelevant.
        parts = root.split(os.sep)
        plugin = parts[-2] if len(parts) >= 2 else ""
        for path in glob.glob(os.path.join(root, "*.md")):
            fm = frontmatter(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            name = fm.get("name", "")
            aliases = {stem, name, f"{plugin}:{stem}", f"{plugin}:{name}"}
            matches = wanted in aliases or (
                bare and bare in {stem, name} and not plugin
            )
            if matches and fm.get("model"):
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
