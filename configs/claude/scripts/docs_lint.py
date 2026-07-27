#!/usr/bin/env python3
"""docs_lint.py - enforce per-document line caps and flag fluff in a docs set.

The docs-* skills need one measurable definition of "concise" rather than a
per-run judgement call, so the caps live in config/doc_limits.yml and this
script is the only thing that reads them. A doc over its cap is a hard finding
(exit 1) because the fix is mechanical: split it into a hub plus sub-pages, per
references/doc-concision.md. Fluff phrases are advisory only -- a wording
blocklist that failed a build would be a blocklist people route around.

Line counting is `wc -l` parity, deliberately including code blocks: the reader
scrolling a 900-line page does not get a discount for the fences.

Usage:
  docs_lint.py [PATHS...] [--limits FILE] [--json PATH] [--warn-only] [--quiet]

Options:
  PATHS         files/dirs to scan (default: current directory)
  --limits FILE caps config (default: repo, then ~/.claude/config/doc_limits.yml)
  --json PATH   also write the machine-readable report to PATH
  --warn-only   report over-cap docs but always exit 0
  --quiet       suppress the per-file table; print the summary only
Exit codes: 0 within caps, 1 at least one doc over cap, 2 usage/unusable input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROG = "docs_lint.py"

# Kept in sync with config/doc_limits.yml. Inlined so the script still works
# from a bare checkout with no config deployed and no PyYAML installed -- a
# lint that cannot run without its own config would be skipped, not fixed.
BUILTIN_LIMITS: dict = {
    "defaults": {"max_lines": 250, "warn_at": 0.8},
    "types": {
        "hub": {"max_lines": 120},
        "readme_root": {"max_lines": 200},
        "tutorial": {"max_lines": 200},
        "howto": {"max_lines": 200},
        "reference": {"max_lines": 400},
        "explanation": {"max_lines": 250},
        "diagram": {"max_lines": 300, "max_diagrams": 4},
    },
    "classify": [
        {"glob": "README.md", "type": "readme_root"},
        {"glob": "**/docs/README.md", "type": "hub"},
        {"glob": "docs/README.md", "type": "hub"},
        {"glob": "**/index.md", "type": "hub"},
    ],
    "exempt": {
        "globs": ["**/node_modules/**", "**/.venv/**", "**/CHANGELOG.md"],
        "markers": ["<!-- generated", "DO NOT EDIT", "AUTO-GENERATED"],
    },
    "overrides": {"type_marker": "doc-type:", "limit_marker": "doc-limit:"},
    "fluff": {"phrases": [], "structure": {}},
}

# Directories never worth walking, independent of the exempt globs.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "site-packages"}

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
MERMAID_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*mermaid\b", re.IGNORECASE)
HRULE_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
TOC_RE = re.compile(r"^#{1,6}\s+(table of contents|contents|toc)\s*$", re.IGNORECASE)
OVERRIDE_RE = re.compile(
    r"<!--\s*(doc-type|doc-limit)\s*:\s*(.+?)\s*-->", re.IGNORECASE
)


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


def glob_to_re(pattern: str) -> re.Pattern[str]:
    """Translate a path glob to a regex.

    fnmatch treats `*` as matching `/` too, which makes `**/x` and `*/x`
    indistinguishable and silently over-matches the exempt list. Translating by
    hand keeps `**` (any depth, including none) separate from `*` (one segment).
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile(f"^{''.join(out)}$")


def matches_any(rel: str, patterns: list[str]) -> bool:
    return any(glob_to_re(p).search(rel) for p in patterns)


def load_limits(explicit: str | None) -> tuple[dict, str]:
    """Return (limits, source). Falls back to BUILTIN_LIMITS, never raises."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    else:
        here = Path(__file__).resolve()
        candidates.append(here.parent.parent / "config" / "doc_limits.yml")
        candidates.append(Path("~/.claude/config/doc_limits.yml").expanduser())

    for path in candidates:
        if not path.is_file():
            continue
        try:
            import yaml  # deferred: an absent PyYAML must not break --help
        except ImportError:
            err("PyYAML not available; using built-in caps")
            return BUILTIN_LIMITS, "built-in (no PyYAML)"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # yaml.YAMLError subclasses ValueError
            err(f"{path}: unreadable ({exc}); using built-in caps")
            return BUILTIN_LIMITS, "built-in (unreadable config)"
        if not isinstance(data, dict):
            err(f"{path}: not a mapping; using built-in caps")
            return BUILTIN_LIMITS, "built-in (bad config)"
        return data, str(path)

    if explicit:
        err(f"{explicit}: no such limits file")
        raise SystemExit(2)
    return BUILTIN_LIMITS, "built-in"


def discover(paths: list[str], root: Path, exempt_globs: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            found.append(p)
            continue
        if not p.is_dir():
            err(f"{raw}: no such file or directory")
            raise SystemExit(2)
        for md in sorted(p.rglob("*.md")):
            if any(part in SKIP_DIRS or part.startswith(".") for part in md.parts[:-1]):
                continue
            found.append(md)
    keep = []
    seen = set()
    for f in found:
        rel = relpath(f, root)
        if rel in seen or matches_any(rel, exempt_globs):
            continue
        seen.add(rel)
        keep.append(f)
    return keep


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def strip_code(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line number, text) for prose lines only.

    Fluff lives in prose. A phrase inside a fenced block or backticks is code
    being quoted, and flagging it trains people to ignore the report.
    """
    out: list[tuple[int, str]] = []
    fence: str | None = None
    for idx, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if fence is not None:
            if m and line.strip().startswith(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)[0] * 3
            continue
        out.append((idx, INLINE_CODE_RE.sub(" ", line)))
    return out


def classify(rel: str, lines: list[str], limits: dict) -> tuple[str, str | None]:
    """Return (type, override_error)."""
    markers = limits.get("overrides", {}) or {}
    type_marker = markers.get("type_marker", "doc-type:")
    for line in lines:
        m = OVERRIDE_RE.search(line)
        if m and f"{m.group(1).lower()}:" == type_marker.lower():
            declared = m.group(2).strip()
            if declared in (limits.get("types") or {}):
                return declared, None
            return "default", f"unknown doc-type '{declared}'"
    for rule in limits.get("classify") or []:
        if glob_to_re(rule.get("glob", "")).search(rel):
            return rule.get("type", "default"), None
    return "default", None


def read_limit_override(
    lines: list[str], limits: dict
) -> tuple[int | None, str | None]:
    """Return (limit, error). A limit override without a rationale is an error.

    Same contract as the help-coverage exemptions: an opt-out nobody can
    evaluate is worse than no opt-out, so the em-dash rationale is mandatory.
    """
    marker = (limits.get("overrides", {}) or {}).get("limit_marker", "doc-limit:")
    for line in lines:
        m = OVERRIDE_RE.search(line)
        if not m or f"{m.group(1).lower()}:" != marker.lower():
            continue
        body = m.group(2)
        num = re.match(r"(\d+)", body.strip())
        if not num:
            return None, "doc-limit override has no number"
        rest = body.strip()[num.end(1) :].strip()
        if not rest.startswith(("—", "--", "-")) or len(rest.lstrip("—- ")) < 10:
            return None, "doc-limit override has no '— <rationale>'"
        return int(num.group(1)), None
    return None, None


def scan_fluff(prose: list[tuple[int, str]], phrases: list[str]) -> list[dict]:
    hits: list[dict] = []
    for num, text in prose:
        low = text.lower()
        for phrase in phrases:
            if phrase.lower() in low:
                hits.append({"line": num, "phrase": phrase})
    return hits


def scan_structure(lines: list[str], total: int, rules: dict) -> list[str]:
    findings: list[str] = []
    toc_below = rules.get("toc_below_lines", 0)
    prose = strip_code(lines)
    if toc_below and total < toc_below:
        for num, text in prose:
            if TOC_RE.match(text):
                findings.append(
                    f"line {num}: hand-maintained TOC on a {total}-line page "
                    "(the renderer makes one; the copy goes stale)"
                )
                break

    per_100 = rules.get("max_hrules_per_100_lines")
    if per_100 and total:
        floor = rules.get("hrule_floor", 4)
        count = sum(1 for _, text in prose if HRULE_RE.match(text))
        density = count * 100 / total
        if count > floor and density > per_100:
            findings.append(
                f"{count} horizontal rules in {total} lines "
                f"({density:.1f}/100 > {per_100}): decoration, not structure"
            )
    return findings


def count_diagrams(lines: list[str]) -> int:
    return sum(1 for line in lines if MERMAID_RE.match(line))


def is_generated(lines: list[str], markers: list[str]) -> bool:
    head = "\n".join(lines[:20])
    return any(m.lower() in head.lower() for m in markers)


def analyze(path: Path, root: Path, limits: dict) -> dict:
    rel = relpath(path, root)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"file": rel, "status": "UNREADABLE", "detail": str(exc)}

    lines = text.splitlines()
    total = len(lines)
    exempt = limits.get("exempt", {}) or {}
    if is_generated(lines, exempt.get("markers") or []):
        return {"file": rel, "status": "GENERATED", "lines": total}

    doc_type, type_err = classify(rel, lines, limits)
    types = limits.get("types") or {}
    defaults = limits.get("defaults") or {}
    spec = types.get(doc_type, {}) or {}
    cap = int(spec.get("max_lines", defaults.get("max_lines", 250)))
    warn_at = float(defaults.get("warn_at", 0.8))

    override, override_err = read_limit_override(lines, limits)
    if override is not None:
        cap = override

    problems: list[str] = []
    for msg in (type_err, override_err):
        if msg:
            problems.append(msg)

    max_diagrams = spec.get("max_diagrams")
    diagrams = count_diagrams(lines) if max_diagrams else 0
    if max_diagrams and diagrams > max_diagrams:
        problems.append(f"{diagrams} diagrams (> {max_diagrams}): split by subject")

    fluff_cfg = limits.get("fluff", {}) or {}
    prose = strip_code(lines)
    fluff = scan_fluff(prose, fluff_cfg.get("phrases") or [])
    structure = scan_structure(lines, total, fluff_cfg.get("structure") or {})

    if total > cap or problems:
        status = "OVER"
    elif total >= cap * warn_at:
        status = "NEAR"
    else:
        status = "OK"

    return {
        "file": rel,
        "type": doc_type,
        "lines": total,
        "cap": cap,
        "status": status,
        "over_by": max(0, total - cap),
        "problems": problems,
        "fluff": fluff,
        "structure": structure,
    }


def render(results: list[dict], source: str, quiet: bool) -> None:
    counted = [r for r in results if r["status"] in ("OK", "NEAR", "OVER")]
    over = [r for r in counted if r["status"] == "OVER"]
    near = [r for r in counted if r["status"] == "NEAR"]
    skipped = [r for r in results if r["status"] in ("GENERATED", "UNREADABLE")]

    if not quiet and counted:
        width = max(len(r["file"]) for r in counted)
        width = min(max(width, 12), 60)
        print(f"{'FILE':<{width}}  {'TYPE':<12} {'LINES':>6} {'CAP':>5}  STATUS")
        for r in sorted(counted, key=lambda r: (-r["over_by"], r["file"])):
            name = r["file"]
            if len(name) > width:
                name = "…" + name[-(width - 1) :]
            extra = f" (+{r['over_by']})" if r["over_by"] else ""
            print(
                f"{name:<{width}}  {r['type']:<12} {r['lines']:>6} "
                f"{r['cap']:>5}  {r['status']}{extra}"
            )
            for msg in r["problems"]:
                print(f"{'':<{width}}  └ {msg}")

    advisories = [(r, m) for r in counted for m in r["structure"]]
    fluff_total = sum(len(r["fluff"]) for r in counted)
    if not quiet and (advisories or fluff_total):
        print()
        print("ADVISORY (never fails the run):")
        for r, msg in advisories:
            print(f"  {r['file']}: {msg}")
        for r in counted:
            for hit in r["fluff"][:5]:
                print(f'  {r["file"]}:{hit["line"]}: fluff "{hit["phrase"]}"')
            if len(r["fluff"]) > 5:
                print(f"  {r['file']}: … {len(r['fluff']) - 5} more fluff hits")

    print()
    print(
        f"{PROG}: {len(counted)} docs, {len(over)} over cap, {len(near)} near cap, "
        f"{fluff_total} fluff hits, {len(skipped)} skipped  [caps: {source}]"
    )
    if over:
        print("Over-cap docs must be split: see references/doc-concision.md")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="Check docs against per-type line caps and flag fluff.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        default=["."],
        metavar="PATHS",
        help="files/dirs to scan (default: current directory)",
    )
    p.add_argument(
        "--limits",
        metavar="FILE",
        default=None,
        help="caps config (default: repo, then ~/.claude/config)",
    )
    p.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="also write the machine-readable report to PATH",
    )
    p.add_argument(
        "--warn-only",
        action="store_true",
        help="report over-cap docs but always exit 0",
    )
    p.add_argument("--quiet", action="store_true", help="print the summary line only")
    args = p.parse_args(argv)

    limits, source = load_limits(args.limits)
    root = Path.cwd().resolve()
    exempt_globs = ((limits.get("exempt") or {}).get("globs")) or []
    files = discover(args.paths or ["."], root, exempt_globs)
    if not files:
        err("no markdown files found")
        return 2

    results = [analyze(f, root, limits) for f in files]
    render(results, source, args.quiet)

    if args.json:
        payload = {"caps_source": source, "results": results}
        try:
            Path(args.json).write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            err(f"{args.json}: {exc}")
            return 2

    over = any(r["status"] == "OVER" for r in results)
    return 1 if (over and not args.warn_only) else 0


if __name__ == "__main__":
    sys.exit(main())
