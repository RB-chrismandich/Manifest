#!/usr/bin/env python3
"""Install one bundle ALONE and prove its cross-skill calls still resolve.

Spec: `docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md`
§4 1.4 "Isolated single-bundle install gate" (Phase 0 item 5).

Two constraints from the spec shape this tool, and both are load-bearing:

1. **It must be a real `claude plugin install`.** Fixture simulation is
   disqualified by the spec's own Cursor argument -- a gate that only indexes a
   marketplace proves nothing about what the harness loads. The sole existing
   precedent (`_plugin_view_fixtures.py::build_fixture_repo`) is exactly that: a
   filesystem simulation that never invokes the CLI.
2. **It does not go in CI yet.** A real install needs headless auth, a sandboxed
   HOME and marketplace network access; none exist in CI today. So this is a
   documented LOCAL pre-release gate, and CI wiring stays deferred as R10 rather
   than silently assumed.

A missing `claude` CLI exits UNVERIFIABLE (2), never 0. The whole point of this
phase is that "a skip that renders as a pass is the false green this phase
exists to remove" -- so the one thing this tool must never do is report success
because it could not run.

HOME is redirected to a scratch directory for the whole probe, so a real
`--scope user` install cannot touch the operator's own `~/.claude`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNVERIFIABLE = 2

_MARKETPLACE = "manifest"


def _run(argv: list[str], env: dict[str, str], timeout: int = 300):
    """Run one native command, never through a shell."""
    return subprocess.run(
        argv, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )


def _declared_closure(checkout: Path, bundle: str) -> set[str]:
    """Bundles the target legitimately pulls in: itself plus any it declares.

    `dependencies` is not represented in the manifest schema yet (tracked
    separately), so today this is the singleton. Written as a set so the
    assertion below does not change shape when it is.
    """
    closure = {bundle}
    manifest = checkout / "plugins" / bundle / "plugin.json"
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return closure
    declared = document.get("dependencies")
    if isinstance(declared, list):
        closure.update(name for name in declared if isinstance(name, str))
    return closure


def _installed_manifest_bundles(env: dict[str, str]) -> tuple[set[str], str | None]:
    listing = _run(["claude", "plugin", "list", "--json"], env)
    if listing.returncode != 0:
        return set(), f"`claude plugin list --json` exited {listing.returncode}"
    try:
        rows = json.loads(listing.stdout)
    except ValueError:
        return set(), "`claude plugin list --json` did not return JSON"
    if isinstance(rows, dict):
        rows = rows.get("plugins", [])
    names = set()
    for row in rows if isinstance(rows, list) else []:
        identifier = row.get("id") or row.get("name") if isinstance(row, dict) else None
        if isinstance(identifier, str):
            names.add(identifier.split("@", 1)[0])
    return names, None


def _snapshot(root: Path) -> set[str]:
    """Relative paths under `root`, for the post-uninstall cleanup comparison."""
    if not root.is_dir():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def probe(bundle: str, checkout: Path) -> tuple[int, dict]:
    """Install `bundle` alone into a scratch HOME and report what resolved."""
    if shutil.which("claude") is None:
        return EXIT_UNVERIFIABLE, {
            "state": "UNVERIFIABLE",
            "reason": "claude CLI not present; this gate requires a real install",
        }
    if not (checkout / ".claude-plugin" / "marketplace.json").is_file():
        return EXIT_UNVERIFIABLE, {
            "state": "UNVERIFIABLE",
            "reason": f"{checkout} does not contain .claude-plugin/marketplace.json",
        }

    findings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="isolated-install-") as scratch:
        home = Path(scratch)
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        before = _snapshot(home)

        added = _run(
            [
                "claude",
                "plugin",
                "marketplace",
                "add",
                str(checkout),
                "--scope",
                "user",
            ],
            env,
        )
        if added.returncode != 0:
            return EXIT_UNVERIFIABLE, {
                "state": "UNVERIFIABLE",
                "reason": f"marketplace add exited {added.returncode}",
                "stderr": added.stderr.strip()[:400],
            }

        installed = _run(
            [
                "claude",
                "plugin",
                "install",
                f"{bundle}@{_MARKETPLACE}",
                "--scope",
                "user",
            ],
            env,
        )
        if installed.returncode != 0:
            return EXIT_FAILED, {
                "state": "FAILED",
                "reason": f"install of {bundle} exited {installed.returncode}",
                "stderr": installed.stderr.strip()[:400],
            }

        present, error = _installed_manifest_bundles(env)
        if error is not None:
            return EXIT_UNVERIFIABLE, {"state": "UNVERIFIABLE", "reason": error}

        expected = _declared_closure(checkout, bundle)
        undeclared = {
            n for n in present if n.startswith(("manifest-", "stitch-"))
        } - expected
        if undeclared:
            findings.append(
                f"installed undeclared sibling bundles: {sorted(undeclared)}"
            )
        if bundle not in present:
            findings.append(f"{bundle} is not in the post-install listing")

        removed = _run(
            ["claude", "plugin", "uninstall", bundle, "--scope", "user"], env
        )
        if removed.returncode != 0:
            findings.append(f"uninstall exited {removed.returncode}")
        # Cleanup is asserted on the REGISTRATION, not on the filesystem tree.
        # `plugin uninstall` deliberately retains plugins/cache/<marketplace>/
        # and plugins/marketplaces/ -- shared marketplace material kept for
        # reinstall, not per-install state. Measured directly rather than
        # assumed: after uninstall, installed_plugins.json goes to [] while the
        # cache directory remains. A tree-diff check here reported 35 surviving
        # paths and every one was cache -- the kind of confident false finding a
        # pre-release gate must never produce.
        still_present, listing_error = _installed_manifest_bundles(env)
        if listing_error is not None:
            findings.append(f"post-uninstall listing unreadable: {listing_error}")
        elif bundle in still_present:
            findings.append(f"{bundle} is still registered after uninstall")
        unexpected_state = {
            path
            for path in _snapshot(home) - before
            if bundle in path
            and "plugins/cache/" not in path
            and "plugins/marketplaces/" not in path
        }
        if unexpected_state:
            findings.append(
                f"{len(unexpected_state)} non-cache path(s) naming {bundle} "
                f"survived uninstall, e.g. {sorted(unexpected_state)[:3]}"
            )

    state = "FAILED" if findings else "OK"
    return (EXIT_FAILED if findings else EXIT_OK), {
        "state": state,
        "bundle": bundle,
        "expected_closure": sorted(expected),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one isolated-install probe."""
    parser = argparse.ArgumentParser(
        description="Install one bundle alone in a scratch HOME and verify its closure.",
        epilog="Exit 0 verified, 1 findings, 2 UNVERIFIABLE (never a silent pass).",
    )
    parser.add_argument("--bundle", required=True, help="bundle to install alone")
    parser.add_argument(
        "--checkout",
        type=Path,
        default=REPO_ROOT,
        help="local marketplace checkout (default: repo root)",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args(argv)

    code, report = probe(args.bundle, args.checkout.resolve())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"state: {report['state']}")
        for key in ("reason", "stderr"):
            if report.get(key):
                print(f"{key}: {report[key]}")
        for finding in report.get("findings", []):
            print(f"  - {finding}")
    return code


if __name__ == "__main__":
    sys.exit(main())
