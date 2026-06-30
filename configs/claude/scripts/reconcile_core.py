#!/usr/bin/env python3
"""Deploy Reconciliation Review — read-only classification core (feature 368).

This is the pure-read engine behind ``deploy_reconcile.sh``: it enumerates
deployed units across the managed assistant homes, dedups shared symlinked
targets by canonical path, classifies orphans KEEP/REMOVE, and renders the
human or ``--json`` report. It performs NO filesystem mutation — the bash
wrapper owns the destructive move/backup (so this module stays safe + testable).

Authoritative interface: specs/368-deploy-orphan-review/contracts/reconcile-cli.md.

v1 scope: reconciles ``~/.claude/skills/*`` (skill dirs) and ``~/.claude/config/*``
(config files) — everything Manifest shares is symlinked into ``~/.claude`` from
the secondary homes, so realpath-dedup collapses the secondary copies onto the
canonical ``~/.claude`` unit and they are reconciled once (FR-017). Real
secondary-home-only artifacts (rules/*.mdc, GEMINI.md, ...) are intentionally not
flagged in v1 (safe under-report). The secondary homes are still scanned to build
the dependent-edge index (FR-015/FR-016).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys

ROOT_TAGS = ("claude", "cursor", "gemini", "codex", "antigravity")
SECONDARY_TAGS = ROOT_TAGS[1:]
# The two managed namespaces reconciled in v1 (relative to each home root).
NAMESPACES = ("skills", "config")


def err(msg):
    sys.stderr.write(f"deploy-reconcile: {msg}\n")


def realpath(path):
    """Portable canonical path (python3, not ``readlink -f``)."""
    return os.path.realpath(path)


def home_root(base, tag):
    return os.path.join(base, f".{tag}")


# --------------------------------------------------------------------------- #
# Protection policy
# --------------------------------------------------------------------------- #
def _parse_protected_yaml(path):
    """Extract ``reconcile.protected`` globs from a YAML file.

    Uses PyYAML when available, else a tiny line parser (so the engine has no
    hard third-party dependency at runtime).
    """
    if not path or not os.path.isfile(path):
        return []
    try:
        import yaml  # type: ignore

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        node = (data.get("reconcile") or {}).get("protected") or []
        return [str(x) for x in node]
    except Exception:
        pass
    # Fallback: parse a flat ``- "glob"`` list under a ``protected:`` key.
    out, in_block = [], False
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.endswith("protected:"):
            in_block = True
            continue
        if in_block:
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                if val:
                    out.append(val)
            elif not line.startswith((" ", "\t")):
                in_block = False
    return out


def load_protection(config_path, local_path, cli_protect):
    """Union of all protection layers (additive; order is irrelevant)."""
    patterns = list(cli_protect or [])
    patterns += _parse_protected_yaml(config_path)
    patterns += _parse_protected_yaml(local_path)
    return patterns


def protect_match(rel_key, patterns):
    """Return the first matching glob, or None. ``*`` spans ``/``; case-sensitive."""
    base = os.path.basename(rel_key)
    for pat in patterns:
        if fnmatch.fnmatchcase(rel_key, pat) or fnmatch.fnmatchcase(base, pat):
            return pat
    return None


# --------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------- #
def _entries(path):
    try:
        return sorted(e for e in os.listdir(path) if e not in (".", ".."))
    except OSError:
        return []


def expected_keys(project):
    """Logical keys the current project would deploy into ~/.claude.

    skills from ``<project>/.skillshare/skills/*``; config from
    ``<project>/configs/claude/config/*``. Returns a set of ``"skills/<name>"`` /
    ``"config/<name>"`` keys.
    """
    keys = set()
    skills_src = os.path.join(project, ".skillshare", "skills")
    for name in _entries(skills_src):
        if os.path.isdir(os.path.join(skills_src, name)):
            keys.add(f"skills/{name}")
    config_src = os.path.join(project, "configs", "claude", "config")
    for name in _entries(config_src):
        keys.add(f"config/{name}")
    return keys


def dependent_edges(base):
    """Reverse-symlink edge index: realpath(target) -> sorted [home tags].

    Bounded to the four secondary homes, depth<=2 (mirrors
    ``find <home> -mindepth 1 -maxdepth 2 -type l``). Broken links are skipped
    (a dangling link is not an active dependent). FR-015/FR-016.
    """
    edges = {}
    for tag in SECONDARY_TAGS:
        root = home_root(base, tag)
        if not os.path.isdir(root):
            continue
        stack = [(root, 0)]
        while stack:
            cur, depth = stack.pop()
            for name in _entries(cur):
                p = os.path.join(cur, name)
                if os.path.islink(p):
                    if os.path.exists(p):  # skip broken/dangling
                        edges.setdefault(realpath(p), set()).add(tag)
                elif os.path.isdir(p) and depth < 1:
                    stack.append((p, depth + 1))
    return {k: sorted(v) for k, v in edges.items()}


def has_active_dependent(canonical, edges):
    """True iff an edge targets this exact canonical path or a path under it
    (namespace-level sharing; a leaf under a still-linked parent is dangle-safe).
    """
    deps = set()
    for target, tags in edges.items():
        if target == canonical or target.startswith(canonical + os.sep):
            deps.update(tags)
    return sorted(deps)


def _claude_units(base, only_root):
    """Enumerate candidate units whose canonical path is under ~/.claude/{skills,config}.

    Scans all 5 homes (so symlinked secondary copies are seen and collapsed), but
    only canonical-under-~/.claude units become candidates. Returns dict
    canonical_path -> {rel_key, unit_type, seen_roots:set}.
    """
    claude_base = realpath(home_root(base, "claude"))
    agent_outputs = os.path.join(claude_base, ".agent_outputs")
    units = {}
    tags = (only_root,) if only_root else ROOT_TAGS
    for tag in tags:
        root = home_root(base, tag)
        for ns in NAMESPACES:
            nsdir = os.path.join(root, ns)
            for name in _entries(nsdir):
                disc = os.path.join(nsdir, name)
                canon = realpath(disc)
                # Only reconcile canonical content under ~/.claude/{skills,config}.
                if canon == agent_outputs:
                    continue
                rel_under = os.path.relpath(canon, claude_base)
                if rel_under.startswith(".."):
                    continue  # canonical lives outside ~/.claude → not a v1 candidate
                top = rel_under.split(os.sep, 1)[0]
                if top not in NAMESPACES:
                    continue
                unit_type = "skill" if top == "skills" else "config"
                rec = units.setdefault(
                    canon,
                    {"rel_key": rel_under, "unit_type": unit_type, "seen_roots": set()},
                )
                rec["seen_roots"].add(tag)
    return units


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def classify(base, project, patterns, only_root=None):
    """Return the list of orphan items (dicts matching contract §7 item shape)."""
    exp = expected_keys(project)
    edges = dependent_edges(base)
    units = _claude_units(base, only_root)
    items = []
    for canon, rec in units.items():
        rel_key = rec["rel_key"]
        if rel_key in exp:
            continue  # reconciled — has a project source
        item = {
            "canonical_path": canon,
            "display_path": _tilde(canon, base),
            "root": "claude",
            "unit_type": rec["unit_type"],
        }
        matched = protect_match(rel_key, patterns)
        deps = has_active_dependent(canon, edges)
        if matched:
            item.update(
                verdict="KEEP",
                reason_code="protected",
                reason=f"protected: {matched}",
                matched_pattern=matched,
                dependents=[],
            )
        elif deps:
            item.update(
                verdict="KEEP",
                reason_code="shared_active_dependents",
                reason=f"shared target — active dependents: {', '.join(deps)}",
                dependents=deps,
            )
        else:
            item.update(
                verdict="REMOVE",
                reason_code="orphan_no_source",
                reason="orphan: no project source",
                dependents=[],
            )
        items.append(item)
    # Stable order: KEEP first then REMOVE, each by display path (matches render).
    items.sort(key=lambda i: (i["verdict"] != "KEEP", i["display_path"]))
    return items


def _tilde(path, base=None):
    """Abbreviate the configured home base (default $HOME) to ``~``."""
    home = os.path.realpath(base) if base else os.path.expanduser("~")
    rp = os.path.realpath(path)
    if rp == home:
        return "~"
    if rp.startswith(home + os.sep):
        return "~" + rp[len(home) :]
    return path


def build_report(base, project, patterns, only_root=None):
    items = classify(base, project, patterns, only_root)
    keep = sum(1 for i in items if i["verdict"] == "KEEP")
    remove = sum(1 for i in items if i["verdict"] == "REMOVE")
    roots = (
        [_tilde(home_root(base, only_root), base)]
        if only_root
        else [_tilde(home_root(base, t), base) for t in ROOT_TAGS]
    )
    return {
        "mode": "preview",
        "project": project,
        "roots": roots,
        "summary": {"orphans": len(items), "keep": keep, "remove": remove},
        "items": items,
        "removed": None,
        "backup_dir": None,
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_human(report):
    n_roots = len(report["roots"])
    plural = "" if n_roots == 1 else "s"
    out = [
        f"deploy-reconcile: review of {n_roots} managed root{plural} (preview — no changes made)",
        "",
    ]
    s = report["summary"]
    keep = [i for i in report["items"] if i["verdict"] == "KEEP"]
    rem = [i for i in report["items"] if i["verdict"] == "REMOVE"]
    if keep:
        out.append(f"KEEP   ({len(keep)})")
        for i in keep:
            out.append(f"  {i['display_path']:<38} ({i['reason']})")
        out.append("")
    if rem:
        out.append(f"REMOVE ({len(rem)})")
        for i in rem:
            out.append(f"  {i['display_path']:<38} ({i['reason']})")
        out.append("")
    out.append(
        f"Summary: {s['orphans']} orphans  |  {s['keep']} KEEP  |  {s['remove']} REMOVE"
    )
    if s["orphans"] == 0:
        out.append("Deployed environment matches the project. No orphans found.")
    elif s["remove"]:
        out.append(
            f"Run with --remove to move the {s['remove']} REMOVE item(s) to a recoverable backup."
        )
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _is_project(path):
    return bool(path) and os.path.isdir(os.path.join(path, "configs", "claude"))


def resolve_project(arg):
    # An explicitly-provided project (flag or env) is authoritative: if it does not
    # resolve, fail (exit 2) rather than silently auto-detecting a different repo.
    if arg is not None:
        return os.path.abspath(arg) if _is_project(arg) else None
    env = os.environ.get("MANIFEST_REPO")
    if env is not None:
        return os.path.abspath(env) if _is_project(env) else None
    # Nothing specified — auto-detect a repo upward from this file's location.
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if _is_project(cur):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--home", default=os.environ.get("MANIFEST_RECONCILE_HOME"))
    ap.add_argument("--project")
    ap.add_argument("--config")
    ap.add_argument("--protect", action="append", default=[])
    ap.add_argument("--root")
    ap.add_argument("--format", choices=("human", "json"), default="human")
    ap.add_argument(
        "--from-json",
        help="render an existing report (path or '-') instead of scanning",
    )
    args = ap.parse_args(argv)

    # Re-render a previously captured report (lets the bash wrapper scan once).
    if args.from_json:
        if args.from_json == "-":
            report = json.load(sys.stdin)
        else:
            with open(args.from_json, encoding="utf-8") as fh:
                report = json.load(fh)
        if args.format == "json":
            sys.stdout.write(json.dumps(report) + "\n")
        else:
            sys.stdout.write(render_human(report) + "\n")
        return 0

    base = args.home or os.path.expanduser("~")
    if args.root and args.root not in ROOT_TAGS:
        err(f"unknown --root '{args.root}' (expected one of: {', '.join(ROOT_TAGS)})")
        return 2
    project = resolve_project(args.project)
    if not project:
        err("cannot resolve project source; pass --project DIR or set MANIFEST_REPO")
        return 2

    config = (
        args.config
        or os.environ.get("RECONCILE_CONFIG")
        or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "config", "reconcile.yml"
        )
    )
    state_root = os.environ.get("MANIFEST_STATE_ROOT") or os.path.join(
        os.path.expanduser("~"), ".manifest"
    )
    local = os.environ.get("MANIFEST_RECONCILE_CONFIG") or os.path.join(
        state_root, "reconcile.local.yml"
    )
    patterns = load_protection(config, local, args.protect)

    report = build_report(base, project, patterns, args.root)
    if args.format == "json":
        sys.stdout.write(json.dumps(report) + "\n")
    else:
        sys.stdout.write(render_human(report) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
