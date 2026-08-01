#!/usr/bin/env python3
"""Resolve and dispatch to the ai-hooks-integration unified hook wherever it
currently lives, so `~/.claude/settings.json` (and the Gemini/Cursor
equivalents) never need hand-editing again when skill storage moves.

Background: skill storage has relocated three times in ~5 weeks -- plain
bootstrap copy to ~/.claude/skills, then apm-managed ~/.manifest/skills, then
plugin bundles under plugins/<bundle>/skills/ (PR #685, apm retirement). Each
move broke the hardcoded absolute path install_all.py had baked into the hook
command string, taking every Bash tool call down until someone noticed and
hand-edited settings.json. See specs/674-plugin-architecture/cutover-plan.md
T4.3 for the first occurrence and its unresolved "the plan has no task
covering why" gap -- the Phase-5 apm stand-down hit the same gap again.

This script lives at ~/.claude/scripts/ -- deployed straight from
configs/claude/scripts/ by bootstrap.sh, untouched by skill/plugin churn -- so
the settings.json command line ("~/.claude/scripts/hook_dispatch.py --source
claude") never has to change again: it resolves the real unified_hook.py and
handler paths at fire-time instead of at install-time.

Fail-open by design: if resolution fails for any reason, this prints the same
allow-response the unified hook itself would and exits 0. A hook that can't
find its own target must never be the thing that blocks every Bash call --
that is exactly the outage this script exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_UNIFIED = (
    "manifest-workspace",
    "ai-hooks-integration",
    "scripts/runtime/unified_hook.py",
)
DEFAULT_HANDLER = ("manifest-forge", "pr-monitor", "scripts/pr_create_trigger.py")

PLUGIN_CACHE_ROOTS = [
    Path(os.environ["HOOK_DISPATCH_CACHE_ROOT"]).expanduser()
    if os.environ.get("HOOK_DISPATCH_CACHE_ROOT")
    else Path.home() / ".claude" / "plugins" / "cache"
]
REPO_FALLBACKS = [
    Path(os.environ["MANIFEST_REPO_DIR"]).expanduser()
    if os.environ.get("MANIFEST_REPO_DIR")
    else None,
    Path.home() / "Documents" / "GitHub" / "Manifest",
]


def _cache_version_dirs(bundle: str) -> list[Path]:
    """Non-orphaned version directories for `bundle`, newest-looking last."""
    found: list[Path] = []
    for cache_root in PLUGIN_CACHE_ROOTS:
        if not cache_root.is_dir():
            continue
        for marketplace_dir in cache_root.iterdir():
            bundle_dir = marketplace_dir / bundle
            if not bundle_dir.is_dir():
                continue
            for version_dir in bundle_dir.iterdir():
                if version_dir.is_dir() and not (version_dir / ".orphaned_at").exists():
                    found.append(version_dir)
    # Version dirs in this repo are plain dotted-integer strings (0.1.0,
    # 0.1.1, ...); lexicographic sort matches semver order for that shape.
    found.sort(key=lambda p: p.name)
    return found


def resolve_skill_script(bundle: str, skill: str, rel_path: str) -> Path | None:
    """Find `rel_path` inside `skill` inside `bundle`, newest cached install first."""
    for version_dir in reversed(_cache_version_dirs(bundle)):
        candidate = version_dir / "skills" / skill / rel_path
        if candidate.is_file():
            return candidate
    for repo_root in REPO_FALLBACKS:
        if repo_root is None:
            continue
        candidate = repo_root / "plugins" / bundle / "skills" / skill / rel_path
        if candidate.is_file():
            return candidate
    return None


def allow_response() -> dict:
    """Same shape unified_hook.py's own fail-open response uses."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        },
        "continue": True,
    }


USAGE = """Usage: hook_dispatch.py --source <claude|gemini|cursor> [options]

Resolve the ai-hooks-integration unified hook and its handler wherever they
currently live (plugin cache, newest non-orphaned version first; falls back to
a repo checkout), then exec them with stdin forwarded unchanged.

  --source SOURCE                 required; forwarded to unified_hook.py --source
  --unified-bundle/-skill/-rel    override the unified hook's location
                                   (default: manifest-workspace ai-hooks-integration
                                   scripts/runtime/unified_hook.py)
  --handler-bundle/-skill/-rel    override the handler's location
                                   (default: manifest-forge pr-monitor
                                   scripts/pr_create_trigger.py)
  --help                          this text

Fails open (prints an allow response, exit 0) if either target can't be
found, so a stale settings.json path can never block a tool call again.
"""


def _build_args() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--source", required=True)
    ap.add_argument("--unified-bundle", default=DEFAULT_UNIFIED[0])
    ap.add_argument("--unified-skill", default=DEFAULT_UNIFIED[1])
    ap.add_argument("--unified-rel", default=DEFAULT_UNIFIED[2])
    ap.add_argument("--handler-bundle", default=DEFAULT_HANDLER[0])
    ap.add_argument("--handler-skill", default=DEFAULT_HANDLER[1])
    ap.add_argument("--handler-rel", default=DEFAULT_HANDLER[2])
    return ap


def main(argv: list[str]) -> int:
    # Before any parsing: without this, --help would be swallowed as a
    # regular flag or misparsed instead of describing the tool.
    if "--help" in argv or "-h" in argv:
        print(USAGE.strip())
        return 0

    args = _build_args().parse_args(argv)

    unified = resolve_skill_script(
        args.unified_bundle, args.unified_skill, args.unified_rel
    )
    handler = resolve_skill_script(
        args.handler_bundle, args.handler_skill, args.handler_rel
    )
    if unified is None or handler is None:
        print(json.dumps(allow_response()))
        return 0

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(unified),
            "--handler",
            str(handler),
            "--source",
            args.source,
        ],
        input=sys.stdin.read(),
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
