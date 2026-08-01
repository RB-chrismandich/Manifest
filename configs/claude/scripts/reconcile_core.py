#!/usr/bin/env python3
# help-coverage: exempt — internal read-only engine behind deploy_reconcile.sh;
# add_help=False, no direct CLI surface (see the module docstring).
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
import importlib.util
import json
import os
import re
import sys

# --------------------------------------------------------------------------- #
# Fleet tags — derived from agent_roster.yml (single enumeration of the
# fleet; see agent_roster.yml's header). Previously a hardcoded tuple; a new
# agent now needs only a registry entry, no source change here
# (tests/python/test_reconcile_policy.py::test_sixth_agent_extends_fleet_via_config_only).
#
# A tag is a MANAGED ROOT: every consumer resolves it to "$HOME/.<tag>"
# (deploy_reconcile.sh, the --root flag, the trash-dir containment check), so
# only roster agents whose home_dir is literally "~/.<name>" may appear here.
# devin is excluded by that rule and deliberately so: its home is
# ~/.config/devin, and "$HOME/.devin" is the Devin *Desktop* app's data
# folder — treating it as a managed root would put an unrelated product's
# files in front of a removal prompt.
# --------------------------------------------------------------------------- #
_DEFAULT_ROOT_TAGS = ("claude", "cursor", "gemini", "codex", "antigravity")


def _default_roster_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config", "agent_roster.yml"
    )


def _agent_roster_loader():
    """Load ``load_agent_roster`` from ``agents/config.py`` WITHOUT importing
    the ``agents`` package. ``agents/__init__.py`` re-exports the full
    orchestration stack (cli/orchestrator/runners/synthesis/validation) —
    heavy and unrelated to this read-only engine — and importing it would
    make PyYAML a hard runtime dependency of this module, which currently has
    none (see ``_parse_protected_yaml`` below). Loaded standalone via
    ``spec_from_file_location``, the same technique
    ``tests/python/test_reconcile_policy.py`` already uses to load this very
    module. Returns None on any failure (missing file, missing PyYAML, ...)
    so callers fall back gracefully.
    """
    try:
        cfg_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "agents", "config.py"
        )
        spec = importlib.util.spec_from_file_location(
            "_reconcile_agents_config", cfg_path
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.load_agent_roster
    except Exception:
        return None


def _is_managed_root(name, home_dir):
    """Whether agent *name* lives at the "$HOME/.<name>" root every fleet-tag
    consumer assumes. A missing home_dir keeps the historical behavior
    (treated as managed) so an older registry is never silently narrowed.
    """
    if not home_dir:
        return True
    return home_dir.strip().strip('"').strip("'") == f"~/.{name}"


def _fallback_roster_tags(path):
    """PyYAML-free extraction of the top-level keys under ``agents:`` whose
    home_dir is a managed "$HOME/.<name>" root — mirrors
    ``_parse_protected_yaml``'s manual fallback parser (no hard yaml
    dependency at runtime).
    """
    if not path or not os.path.isfile(path):
        return []
    tags, in_block = [], False
    name, home = None, None

    def flush():
        if name is not None and _is_managed_root(name, home):
            tags.append(name)

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if line == "agents:":
                in_block = True
                continue
            if in_block:
                if (
                    line.startswith("  ")
                    and not line.startswith("    ")
                    and stripped.endswith(":")
                ):
                    flush()
                    name, home = stripped[:-1], None
                elif line.startswith("    ") and stripped.startswith("home_dir:"):
                    home = stripped.split(":", 1)[1].strip()
                elif not line.startswith(" "):
                    break
    flush()
    return tags


def _order_tags(tags):
    """Order tags to match the historical ``ROOT_TAGS`` order for the 5 known
    agents exactly, regardless of the registry's own key order (drift-safe:
    ``agent_roster.yml`` lists ``gemini`` before ``cursor``) — this is a
    drop-in data-source swap, not a redesign, so the 5-agent output (roots
    listing, ``--root`` error message) must stay byte-identical. A tag not in
    the historical set (e.g. a config-only 6th agent) is appended afterward,
    in the order the registry declared it.
    """
    known_order = {t: i for i, t in enumerate(_DEFAULT_ROOT_TAGS)}
    known = sorted((t for t in tags if t in known_order), key=lambda t: known_order[t])
    extra = [t for t in tags if t not in known_order]
    return known + extra


def load_fleet_tags(roster_path=None):
    """The fleet tag tuple, derived from ``agent_roster.yml``.

    Resolution order: explicit ``roster_path`` arg > ``MANIFEST_AGENT_ROSTER``
    env var (mirrors ``RECONCILE_CONFIG``/``MANIFEST_RECONCILE_CONFIG``
    below) > the sibling ``../config/agent_roster.yml``. Only agents whose
    home_dir is a managed "$HOME/.<name>" root are returned (see the
    _DEFAULT_ROOT_TAGS header). Falls back to the hardcoded 5-tag default if
    the registry is missing, unparseable, or the
    ``agents/config.py`` loader can't be imported — this CLI must keep
    working with no config file present (same invariant as
    ``_parse_protected_yaml``).
    """
    path = (
        roster_path or os.environ.get("MANIFEST_AGENT_ROSTER") or _default_roster_path()
    )
    tags = []
    loader = _agent_roster_loader()
    if loader is not None:
        try:
            roster = loader(path)
            if isinstance(roster, dict) and roster:
                tags = [
                    name
                    for name, entry in roster.items()
                    if _is_managed_root(
                        name,
                        entry.get("home_dir") if isinstance(entry, dict) else None,
                    )
                ]
        except Exception:
            tags = []
    if not tags:
        tags = _fallback_roster_tags(path)
    if not tags:
        return _DEFAULT_ROOT_TAGS
    return tuple(_order_tags(tags))


ROOT_TAGS = load_fleet_tags()
SECONDARY_TAGS = ROOT_TAGS[1:]
# Managed namespaces reconciled per home root (v1: skills+config; v2 adds
# scripts — deployed tooling drift was invisible before, issue #462).
NAMESPACES = ("skills", "config", "scripts", "prompts")


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

    skills from ``<project>/.apm/skills/*``; config from
    ``<project>/configs/claude/config/*``; scripts from
    ``<project>/configs/claude/scripts/*``; prompts from
    ``<project>/configs/claude/prompts/*``. Returns a set of
    ``"skills/<name>"`` / ``"config/<name>"`` / ``"scripts/<name>"`` /
    ``"prompts/<name>"`` keys.
    """
    keys = set()
    skills_src = os.path.join(project, ".apm", "skills")
    for name in _entries(skills_src):
        path = os.path.join(skills_src, name)
        if os.path.isdir(path):
            keys.add(f"skills/{name}")
        elif os.path.isfile(path) and not name.startswith("."):
            # Repo-sourced top-level files (e.g. README.md) deploy with every
            # bootstrap; hidden entries are not reconciled units.
            keys.add(f"skills/{name}")
    config_src = os.path.join(project, "configs", "claude", "config")
    for name in _entries(config_src):
        keys.add(f"config/{name}")
    scripts_src = os.path.join(project, "configs", "claude", "scripts")
    for name in _entries(scripts_src):
        if not name.startswith("."):
            keys.add(f"scripts/{name}")
    prompts_src = os.path.join(project, "configs", "claude", "prompts")
    for name in _entries(prompts_src):
        if not name.startswith("."):
            keys.add(f"prompts/{name}")
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
    """Enumerate candidate units whose canonical path is under ~/.claude/{skills,config,scripts}.

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
                # Only reconcile canonical content under a managed namespace.
                if canon == agent_outputs:
                    continue
                rel_under = os.path.relpath(canon, claude_base)
                if rel_under.startswith(".."):
                    continue  # canonical lives outside ~/.claude → not a v1 candidate
                top = rel_under.split(os.sep, 1)[0]
                if top not in NAMESPACES:
                    continue
                unit_type = {
                    "skills": "skill",
                    "scripts": "script",
                    "prompts": "prompt",
                }.get(top, "config")
                rec = units.setdefault(
                    canon,
                    {"rel_key": rel_under, "unit_type": unit_type, "seen_roots": set()},
                )
                rec["seen_roots"].add(tag)
    return units


def registry_skill_names(project):
    """Skill names ``skill_policies.yml`` says this project ships (T1.8, spec 674).

    Returns ``None`` when the project has no registry, which is meaningfully
    different from an empty set:

      * ``None``  -- not a Manifest project. Protect nothing under ``skills/``;
        behave exactly as this engine did before.
      * ``set()`` -- a Manifest project that ships no skills. Every entry in the
        tree is then somebody else's, and all of it is protected.

    Getting that distinction wrong in either direction is a silent failure. A
    blanket ``skills/*`` protection disables orphan detection for the whole tree
    -- the same class as the incident that ate ``deploy_stamp``/``.migrated``,
    only inverted. Treating a missing registry as "ships nothing" would do it on
    every non-Manifest project at once.
    """
    if not project:
        return None
    path = os.path.join(project, "configs", "claude", "config", "skill_policies.yml")
    if not os.path.isfile(path):
        return None
    names = set()
    in_bundles = False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.split("#", 1)[0].rstrip()
                if stripped[:1] not in (" ", "", "\t"):
                    in_bundles = stripped.startswith("bundles:")
                    continue
                if in_bundles and stripped.startswith("    - "):
                    names.add(stripped[6:].strip())
    except OSError:
        return None
    return names


def user_owned_skill(rel_key, registry):
    """Is this a skill directory the project never shipped?

    ``claude plugin init <name>`` scaffolds into ``~/.claude/skills/<name>/`` and
    auto-loads it as ``<name>@skills-dir``. Once Manifest stops sourcing that
    tree, every such directory looks exactly like an orphan.
    """
    if registry is None:
        return False
    parts = rel_key.split("/")
    if len(parts) < 2 or parts[0] != "skills":
        return False
    name = parts[1]
    # Dotfiles in the tree are handled by the explicit globs, not by name.
    return not name.startswith(".") and name not in registry


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def classify(base, project, patterns, only_root=None):
    """Return the list of orphan items (dicts matching contract §7 item shape)."""
    exp = expected_keys(project)
    edges = dependent_edges(base)
    registry = registry_skill_names(project)
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
        if not matched and user_owned_skill(rel_key, registry):
            # Reported under its own reason_code rather than dressed up as a
            # glob match: "protected: skills/*" would claim a pattern the
            # config does not contain, and the whole point of this verdict is
            # that the config CANNOT name it -- the user chose the name.
            item.update(
                verdict="KEEP",
                reason_code="user_owned_skill",
                reason="user-owned: not in skill_policies.yml",
                matched_pattern=None,
                dependents=[],
            )
        elif matched:
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


_ENTRY_POINT_RE = re.compile(r"~/\.claude/scripts/([A-Za-z0-9_][A-Za-z0-9_./-]*)")


def entry_point_warnings(base):
    """Warn when a deployed skill references a ~/.claude/scripts entry point
    that is not deployed — the /deploy-reconcile-without-its-script failure
    mode (issue #462). Read-only; returns sorted human-readable warnings.
    """
    claude_base = realpath(home_root(base, "claude"))
    skills_dir = os.path.join(claude_base, "skills")
    warnings = set()
    for name in _entries(skills_dir):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        try:
            with open(skill_md, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        scripts_root = os.path.join(claude_base, "scripts")
        for ref in _ENTRY_POINT_RE.findall(text):
            ref = ref.rstrip(".")
            # Containment guard: a ref with '..' segments must not let the
            # existence check escape ~/.claude/scripts (review 3511352386);
            # an escaping ref is by definition not a deployed entry point.
            target = os.path.normpath(os.path.join(scripts_root, ref))
            inside = target == scripts_root or target.startswith(scripts_root + os.sep)
            if not inside or not os.path.exists(target):
                warnings.add(
                    f"skill '{name}' references ~/.claude/scripts/{ref} which is not deployed"
                )
    return sorted(warnings)


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
        "warnings": entry_point_warnings(base),
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
    warns = report.get("warnings") or []
    if warns:
        out.append("")
        out.append(f"Warnings ({len(warns)}):")
        for w in warns:
            out.append(f"  ! {w}")
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
    ap.add_argument(
        "--list-tags",
        action="store_true",
        help="print the fleet tag list (one per line, agent_roster.yml-derived) and exit",
    )
    args = ap.parse_args(argv)

    # Machine-readable fleet list for the bash wrapper (deploy_reconcile.sh) —
    # needs no project/home resolution, mirrors the --from-json short-circuit.
    if args.list_tags:
        sys.stdout.write("\n".join(ROOT_TAGS) + "\n")
        return 0

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
