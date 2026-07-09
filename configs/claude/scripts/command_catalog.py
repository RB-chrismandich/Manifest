#!/usr/bin/env python3
"""Build the machine catalog of Manifest commands from the skill source of truth.

Parses every ``.skillshare/skills/*/SKILL.md`` frontmatter (the single source of
truth — spec 362, FR-003) into an in-memory catalog, deriving the "when to use"
cue, resolving each command's category against the curated taxonomy, and
computing availability. The catalog is a pure function of (skill sources,
``command_categories.yml``, ``services.yml``, platform), which is what makes the
drift-check and reproducible tests possible (contracts/catalog-schema.md).

CLI:
    command_catalog.py [--json] [--platform <name>]
        --json       machine catalog (catalog-schema.md); default = human summary
        --platform   active platform for availability resolution (default: detect)

Env overrides (tests):
    COMMAND_CATALOG_SKILLS_DIR, COMMAND_CATALOG_CATEGORIES, COMMAND_CATALOG_SERVICES
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):(.*)$")
_BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?$")

PROG = "command_catalog.py"

# Repo-relative defaults (script lives in configs/claude/scripts/).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SKILLS_DIR = _REPO_ROOT / ".skillshare" / "skills"
DEFAULT_CATEGORIES = (
    _REPO_ROOT / "configs" / "claude" / "config" / "command_categories.yml"
)
DEFAULT_SERVICES = _REPO_ROOT / "configs" / "claude" / "config" / "services.yml"

DEFAULT_PLATFORM = "claude"
UNCATEGORIZED = "uncategorized"
DEFAULT_LIMIT = 30  # default row cap for discovery output (context-budget guard)

# A skill is gated by a service only when its name carries one of these prefixes
# (D6 — availability is inferred from signals that already exist; no new
# per-skill frontmatter). Everything else is service-ungated (always enabled).
SERVICE_PREFIXES = {
    "skillclaw": "skillclaw",
}


class CatalogError(Exception):
    """Raised on a malformed/duplicate/empty skill or an invalid category."""


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Derivation helpers
# --------------------------------------------------------------------------- #
def _humanize(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").strip().capitalize()


def _first_sentence(text: str) -> str:
    """First sentence of a flattened description (terminator kept)."""
    flat = " ".join(text.split())
    for i, ch in enumerate(flat):
        if ch in ".!?":
            return flat[: i + 1].strip()
    return flat.strip()


def derive_when_to_use(description: str, name: str) -> str:
    """Derive the when-to-use cue (D2) without inventing text.

    Chain: (1) an explicit "Use when …" clause → (2) first sentence of the
    description → (3) humanized name. Never returns empty.
    """
    flat = " ".join((description or "").split())
    lowered = flat.lower()
    idx = lowered.find("use when")
    if idx != -1:
        clause = flat[idx:]
        # Trim to the first sentence-ending punctuation or em-dash boundary.
        for i, ch in enumerate(clause):
            if ch in ".!?":
                return clause[: i + 1].strip()
        return clause.strip()
    sentence = _first_sentence(flat)
    if sentence:
        return sentence
    return _humanize(name)


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #
def load_categories(path: str):
    """Return (ordered categories list, overrides map, valid key set)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw = data.get("categories") or []
    categories = sorted(
        ({"key": c["key"], "label": c["label"], "order": int(c["order"])} for c in raw),
        key=lambda c: c["order"],
    )
    overrides = data.get("overrides") or {}
    valid = {c["key"] for c in categories}
    return categories, overrides, valid


def load_services(path: str) -> dict:
    if not path or not Path(path).exists():
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data.get("services") or {}


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def resolve_category(frontmatter_cat, name, valid_keys, overrides) -> str:
    """Precedence (D1): frontmatter > overrides map > uncategorized."""
    if frontmatter_cat:
        if frontmatter_cat not in valid_keys:
            raise CatalogError(
                f"{name}: unknown category '{frontmatter_cat}' "
                f"(not in command_categories.yml)"
            )
        return frontmatter_cat
    if name in overrides:
        ov = overrides[name]
        if ov not in valid_keys:
            raise CatalogError(
                f"overrides['{name}'] = '{ov}' is not a valid category key"
            )
        return ov
    return UNCATEGORIZED


def _service_for(name: str) -> str | None:
    for prefix, service in SERVICE_PREFIXES.items():
        if (
            name == prefix
            or name.startswith(prefix + "-")
            or name.startswith(prefix + "_")
        ):
            return service
    return None


def resolve_availability(name: str, services: dict, platform: str) -> dict:
    """Availability (D6): available iff owning service enabled AND deployed.

    Skills deploy to every platform via the symlink chain, so
    ``deployed_to_platform`` defaults True; the only gate that exists today is
    the owning service's ``enabled`` flag in services.yml.
    """
    service = _service_for(name)
    service_enabled = True
    if service is not None:
        cfg = services.get(service) or {}
        flag = cfg.get("enabled", True)
        # `auto` (git_cli) is treated as enabled for discovery purposes.
        service_enabled = flag is True or flag == "auto"

    deployed = True  # symlink chain deploys skills to all platforms

    if service_enabled and deployed:
        return {
            "service_enabled": True,
            "deployed_to_platform": True,
            "status": "available",
            "reason": None,
        }
    reason = (
        "service disabled" if not service_enabled else f"not deployed on {platform}"
    )
    return {
        "service_enabled": service_enabled,
        "deployed_to_platform": deployed,
        "status": "unavailable",
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        inner = v[1:-1]
        if v[0] == '"':
            # YAML-unescape the double-quoted scalar body: strip the outer
            # quotes above, then undo backslash escaping so callers get the
            # literal text (a raw " and \). Python twin of the bash fix in
            # bd2738e (generate_cursor_rules.sh) — without this, a
            # description like "... \"phrase\" ..." would leave the parsed
            # value holding the literal `\"` instead of `"`.
            #
            # Order matters: unescape \" -> " before \\ -> \. Reversing it is
            # wrong — e.g. raw `\\"` (escaped-backslash + delimiter quote)
            # must decode to `\"` (a literal backslash then a literal quote).
            # Unescaping \\ first collapses it to a single backslash sitting
            # right before the quote, and the second pass then misreads that
            # backslash+quote pair as an escaped-quote sequence, stripping
            # the backslash and losing a character (`\\"` -> `"`, wrong).
            # Doing \" first avoids this: real \" pairs are consumed while
            # any \\ pairs are still intact (two chars), so they can't be
            # mistaken for an escaped quote.
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            # Single-quoted YAML escapes an embedded quote as ''; no current
            # SKILL.md description uses single quotes, but handle it for
            # correctness/parity with the double-quoted path above.
            inner = inner.replace("''", "'")
        return inner
    return v


def _parse_frontmatter(text: str, path: Path) -> dict:
    """Tolerant frontmatter reader for `name`/`description`/`category`.

    Deliberately does NOT feed the frontmatter to ``yaml.safe_load``: real
    SKILL.md descriptions are plain scalars that legitimately contain ``: ``
    (e.g. "pwn-request issues: fork head-ref…"), which strict YAML rejects.
    This mirrors the line-based extraction in ``generate_cursor_rules.sh``.
    Handles inline values (quoted or plain) and block scalars (``|``/``>`` with
    optional ``+``/``-``), flattening block scalars to a single line.
    """
    if not text.startswith("---"):
        raise CatalogError(f"{path}: missing YAML frontmatter")
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise CatalogError(f"{path}: unterminated frontmatter")

    body = lines[1:end]
    fields: dict[str, str | None] = {}
    i = 0
    while i < len(body):
        match = _KEY_RE.match(body[i])
        if not match:
            i += 1
            continue
        key, rest = match.group(1), match.group(2).strip()
        if key not in ("name", "description", "category"):
            i += 1
            continue
        if key == "description" and (rest == "" or _BLOCK_SCALAR_RE.match(rest)):
            collected, j = [], i + 1
            while j < len(body):
                cont = body[j]
                if cont.strip() == "":
                    collected.append("")
                    j += 1
                    continue
                if not cont.startswith((" ", "\t")):  # dedent → end of block
                    break
                collected.append(cont.strip())
                j += 1
            fields[key] = " ".join(c for c in collected if c).strip()
            i = j
        else:
            fields[key] = _strip_quotes(rest)
            i += 1
    return fields


def parse_skill(skill_md: Path) -> dict:
    fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"), skill_md)
    name = (fm.get("name") or "").strip()
    if not name:
        raise CatalogError(f"{skill_md}: missing 'name' in frontmatter")
    description = (fm.get("description") or "").strip()
    if not description:
        raise CatalogError(f"{skill_md}: empty 'description' (malformed skill)")
    category = fm.get("category")
    return {
        "name": name,
        "description": description,
        "category": category,
        "path": skill_md,
    }


def _iter_skill_files(skills_dir: Path):
    """Yield each SKILL.md, following symlinked skill directories (repo convention)."""
    if not skills_dir.exists():
        raise CatalogError(f"skills directory not found: {skills_dir}")
    for child in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        # follow symlinks; a skill dir may be reached via a symlink
        if not (child.is_dir() or (child.is_symlink() and child.resolve().is_dir())):
            continue
        skill_md = child / "SKILL.md"
        if skill_md.exists():
            yield skill_md


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
def build_catalog(
    skills_dir: str | None = None,
    categories_path: str | None = None,
    services_path: str | None = None,
    platform: str | None = None,
) -> dict:
    skills_dir = Path(
        skills_dir or os.environ.get("COMMAND_CATALOG_SKILLS_DIR") or DEFAULT_SKILLS_DIR
    )
    categories_path = (
        categories_path
        or os.environ.get("COMMAND_CATALOG_CATEGORIES")
        or str(DEFAULT_CATEGORIES)
    )
    services_path = (
        services_path
        or os.environ.get("COMMAND_CATALOG_SERVICES")
        or str(DEFAULT_SERVICES)
    )
    platform = platform or DEFAULT_PLATFORM

    categories, overrides, valid_keys = load_categories(categories_path)
    services = load_services(services_path)

    cat_order = {c["key"]: c["order"] for c in categories}
    cat_order[UNCATEGORIZED] = max(cat_order.values(), default=0) + 1

    commands = []
    seen: dict[str, Path] = {}
    for skill_md in _iter_skill_files(skills_dir):
        sk = parse_skill(skill_md)
        name = sk["name"]
        if name in seen:
            raise CatalogError(
                f"duplicate command name '{name}' ({seen[name]} and {skill_md})"
            )
        seen[name] = skill_md
        category = resolve_category(sk["category"], name, valid_keys, overrides)
        commands.append(
            {
                "name": name,
                "description": sk["description"],
                "when_to_use": derive_when_to_use(sk["description"], name),
                "category": category,
                "availability": resolve_availability(name, services, platform),
            }
        )

    commands.sort(key=lambda c: (cat_order.get(c["category"], 999), c["name"]))
    return {
        "generated_for_platform": platform,
        "categories": categories,
        "commands": commands,
    }


# --------------------------------------------------------------------------- #
# Discovery (the /help surface — contracts/discovery-command.md, D7)
# --------------------------------------------------------------------------- #
def search_rank(commands, query: str):
    """Weighted, deterministic ranking: name > category > description/when-to-use;
    ties broken alphabetically. Returns only commands with a non-zero score."""
    q = query.lower().strip()
    scored = []
    for c in commands:
        score = 0
        name = c["name"].lower()
        if q == name:
            score += 3000
        elif name.startswith(q):
            score += 1500
        elif q in name:
            score += 1000
        if q in c["category"].lower():
            score += 100
        if q in (c["description"] + " " + c["when_to_use"]).lower():
            score += 10
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda t: (-t[0], t[1]["name"]))
    return [c for _, c in scored]


def _row(c: dict) -> str:
    base = f"`/{c['name']}` — {c['description']} _({c['when_to_use']})_"
    if c["availability"]["status"] != "available":
        base += f" — unavailable: {c['availability']['reason']}"
    return base


def format_listing(
    catalog, query=None, category=None, show_all=False, limit=DEFAULT_LIMIT
) -> str:
    """Render the discovery listing. Empty query → grouped by category; query →
    ranked flat list. Output is bounded by `limit` with an 'N more' footer."""
    labels = {c["key"]: c["label"] for c in catalog["categories"]}
    labels[UNCATEGORIZED] = "Uncategorized"
    order = {c["key"]: c["order"] for c in catalog["categories"]}
    order[UNCATEGORIZED] = max(order.values(), default=0) + 1

    cmds = catalog["commands"]
    if category:
        cmds = [c for c in cmds if c["category"] == category]
    if not show_all:
        cmds = [c for c in cmds if c["availability"]["status"] == "available"]

    footer = "… {n} more — narrow with /help <query>"

    if query:
        ranked = search_rank(cmds, query)
        if not ranked:
            return f'No command matches "{query}".'
        shown = ranked[:limit]
        lines = [_row(c) for c in shown]
        remaining = len(ranked) - len(shown)
        if remaining > 0:
            lines.append(footer.format(n=remaining))
        return "\n".join(lines)

    ordered = sorted(cmds, key=lambda c: (order.get(c["category"], 999), c["name"]))
    shown = ordered[:limit]
    lines, current = [], None
    for c in shown:
        if c["category"] != current:
            current = c["category"]
            lines.append("")
            lines.append(f"## {labels.get(current, current)}")
        lines.append(_row(c))
    remaining = len(ordered) - len(shown)
    if remaining > 0:
        lines.append("")
        lines.append(footer.format(n=remaining) + " or raise --limit")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="Discover Manifest commands (the /help surface) or emit the "
        "machine catalog built from SKILL.md frontmatter.",
    )
    p.add_argument(
        "query",
        nargs="?",
        default=None,
        help="intent/keyword search over name, category, description",
    )
    p.add_argument("--json", action="store_true", help="emit machine catalog JSON")
    p.add_argument("--category", default=None, help="restrict to one taxonomy category")
    p.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="include unavailable commands (marked with a reason)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"cap rows shown (default {DEFAULT_LIMIT})",
    )
    p.add_argument(
        "--platform", default=None, help="platform for availability resolution"
    )
    return p


def main(argv=None) -> int:
    # --help must succeed before any catalog/config load (repo convention:
    # cli-audit-help). argparse handles -h/--help here,
    # before build_catalog() touches the filesystem.
    args = _build_parser().parse_args(argv)
    try:
        catalog = build_catalog(platform=args.platform)
    except CatalogError as exc:
        err(str(exc))
        return 1
    if args.json:
        print(json.dumps(catalog, indent=2))
    else:
        print(
            format_listing(
                catalog,
                query=args.query,
                category=args.category,
                show_all=args.show_all,
                limit=args.limit,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
