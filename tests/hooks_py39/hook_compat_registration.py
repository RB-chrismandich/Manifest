"""Load hook cases and verify deployed hook registrations."""

import json
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((Path(__file__).parent / "hook_cases.yaml").read_text())
PYTHON_CASES = CASES["python_cases"]
PLUGIN_CASES = CASES["plugin_cases"]
SCRIPTS = ROOT / "configs/claude/scripts"
PLUGIN_HOOK_IDENTITIES = {
    (case["plugin"], case["script"], case["event"], case["matcher"])
    for case in PLUGIN_CASES
}


def command_entry(event, entries, script):
    """Return a registered command's event and matcher."""
    for entry in entries:
        for hook in entry.get("hooks", []):
            if script in hook.get("command", ""):
                return event, entry.get("matcher", "")
    return None


def registered_plugin_python_hooks():
    """Return every plugin Python hook declared in a hooks manifest."""
    found = set()
    for manifest_path in (ROOT / "plugins").glob("*/hooks/*.json"):
        plugin = manifest_path.parents[1].name
        manifest = json.loads(manifest_path.read_text())
        for event, entries in manifest.get("hooks", {}).items():
            for entry in entries:
                matcher = entry.get("matcher", "")
                for hook in entry.get("hooks", []):
                    command = hook.get("command", "")
                    for token in shlex.split(command):
                        if ".py" not in token:
                            continue
                        script = token.split("${CLAUDE_PLUGIN_ROOT}/", 1)[-1]
                        if script.endswith(".py"):
                            found.add((plugin, script, event, matcher))
    return found


def verify_registrations():
    """Assert case coverage and special shell/plugin registration contracts."""
    settings = json.loads((ROOT / "configs/claude/settings.runtime.json").read_text())
    registered = set()
    for event, entries in settings["hooks"].items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                for token in shlex.split(hook.get("command", "")):
                    if token.endswith(".py"):
                        registered.add(
                            (Path(token).name, event, entry.get("matcher", ""))
                        )
                        break
    expected = {
        (name, case["event"], case["matcher"]) for name, case in PYTHON_CASES.items()
    }
    if registered != expected:
        raise AssertionError(
            "Python hook inventory mismatch: missing="
            + repr(registered - expected)
            + " stale="
            + repr(expected - registered)
        )
    discovered = registered_plugin_python_hooks()
    if discovered != PLUGIN_HOOK_IDENTITIES:
        raise AssertionError(
            "plugin Python hook inventory mismatch: missing="
            + repr(discovered - PLUGIN_HOOK_IDENTITIES)
            + " stale="
            + repr(PLUGIN_HOOK_IDENTITIES - discovered)
        )
    _verify_special_registrations(settings)


def _verify_special_registrations(settings):
    stop = json.loads((ROOT / "plugins/manifest-delegate/hooks/hooks.json").read_text())
    if command_entry("Stop", stop["hooks"]["Stop"], "stop_gate_hook.sh") != (
        "Stop",
        "",
    ):
        raise AssertionError("manifest-delegate Stop registration mismatch")
    checks = (
        ("lint_on_edit_hook.sh", None, ("Write|Edit",)),
        (
            "spec_review.sh",
            ("PostToolUse", "Write|Edit"),
            ("PostToolUse", "Write|Edit"),
        ),
    )
    for needle, wanted, _ in checks:
        actual = None
        for event, entries in settings["hooks"].items():
            for entry in entries:
                if any(
                    needle in hook.get("command", "") for hook in entry.get("hooks", [])
                ):
                    actual = (
                        (event, entry.get("matcher", ""))
                        if wanted
                        else (entry.get("matcher", ""),)
                    )
        expected = wanted if wanted else ("Write|Edit",)
        if actual != expected:
            raise AssertionError(f"{needle} registration mismatch: {actual!r}")
    manifest = json.loads(
        (ROOT / "plugins/manifest-ops/hooks/version-pin.json").read_text()
    )
    registration = command_entry(
        "PostToolUse", manifest["hooks"]["PostToolUse"], "version_pin_hook.sh"
    )
    if registration != ("PostToolUse", "Write|Edit"):
        raise AssertionError("version-pin hook registration mismatch")
