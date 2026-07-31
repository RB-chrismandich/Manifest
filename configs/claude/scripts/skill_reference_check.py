#!/usr/bin/env python3
"""Cross-skill reference gate for the plugin cutover (T1.3, spec 674).

Post-cutover a plugin skill is reachable ONLY as ``<plugin>:<skill>``, so every
bare cross-skill reference inside a skill body stops resolving. The failure is
silent: a sub-agent handed an unresolvable name improvises and reports success.

This gate exists because the obvious implementation -- grep for ``/<name>`` --
catches only the references that carry a slash. The measured surface splits:

    slash      20 sites   ``Run `/project-verify` ``        <- a slash grep sees these
    dispatch   15 sites   ``run `docs-improve-readme` ``    <- and is blind to these
    prose     122 sites   ``see also `pr-review` ``         <- cosmetic, baselined
    relative    4 sites   ``../extract-static-html/SKILL.md`` <- a file path, not a command

Counts are as measured on 2026-07-30; run the tool for current figures rather
than trusting this comment.

``docs-all`` lives entirely in the dispatch class: it dispatches three skills by
bare name and prints a per-skill success table. A slash-only gate ships green
over exactly the skill whose failure mode is a fabricated success report.

Exit codes: 0 clean, 1 blocking references (or warnings above baseline), 2 usage.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

USAGE = """\
Usage: skill_reference_check.py [--roots P[:P...]] [--baseline F] [--json] [--help]

Find cross-skill references that stop resolving once skills are plugin-scoped.

  --roots P[:P...]  Skill root dirs (default: plugins/*/skills, else the
                    .apm/skills mirror). Colon-separated.
  --baseline F      JSON ratchet: warning_total / blocking_total ceilings.
  --registry F      skill_policies.yml; its expected_total must equal the
                    catalog found on disk. Exogenous check against silent loss.
  --json            Machine-readable report on stdout.
  --help            This text.

Blocking: slash-form refs, and bare names on a dispatch line. Warning: bare
names in prose. Qualified refs and {{skill:<name>}} are the fix, never flagged.
"""

DISPATCH_VERBS = re.compile(
    r"\b(run|runs|invoke|invokes|dispatch|dispatches|delegate|delegates"
    r"|call|calls|launch|launches|execute|executes|hand[- ]off|sub-?agent)\b",
    re.IGNORECASE,
)

MASK = "\x00"


def err(message: str) -> None:
    """Route every diagnostic to stderr so --json stdout stays parseable."""
    print(f"skill_reference_check.py: {message}", file=sys.stderr)


@dataclass
class Hit:
    """One cross-skill reference: who points at whom, how, and exactly where."""

    source: str
    target: str
    kind: str
    file: str
    line: int
    text: str


@dataclass
class Report:
    """Hits split by consequence: blocking breaks at runtime, warning breaks the
    name a reader is told to type, relative is a file path that survives inside
    a bundle. The split is the point -- one number would hide the dangerous set."""

    blocking: list[Hit] = field(default_factory=list)
    warning: list[Hit] = field(default_factory=list)
    relative: list[Hit] = field(default_factory=list)

    def as_dict(self) -> dict:
        """Stable JSON shape: three counts plus the three full hit lists."""

        def dump(hits: list[Hit]) -> list[dict]:
            """Hit -> plain dict, field order preserved for readable diffs."""
            return [vars(h) for h in hits]

        return {
            "blocking_count": len(self.blocking),
            "warning_count": len(self.warning),
            "relative_link_count": len(self.relative),
            "blocking": dump(self.blocking),
            "warning": dump(self.warning),
            "relative": dump(self.relative),
        }


def build_catalog(roots: list[Path]) -> set[str]:
    """Skill names are directory names. Derived from the tree, never hardcoded,
    so the gate cannot drift from the catalog it guards."""
    names: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        names.update(
            p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
    return names


def masked_lines(body: str) -> list[tuple[str, bool]]:
    """(line, is_fenced) per body line.

    HTML comments are blanked outright -- they are inert. Fenced code is NOT
    dropped, only flagged: a fenced shell example invoking `/project-verify`
    breaks after the cutover exactly like a prose one, so discarding fences
    would hide real breaks. Callers demote fenced hits to the warning tier
    instead, which keeps them counted without failing the build on a worked
    example of the syntax being deprecated.

    Line count is preserved so reported line numbers stay true.
    """
    lines = body.splitlines()
    # Unbalanced markers mean the fences cannot be trusted. Scanning the tail as
    # fenced would silently stop looking -- a gate must fail toward MORE
    # scrutiny, never less. Real case: session-checkpoint/SKILL.md has 11
    # markers because it writes ```text where a bare ``` should close.
    balanced = (
        sum(1 for line in lines if line.lstrip().startswith(("```", "~~~"))) % 2 == 0
    )

    out: list[tuple[str, bool]] = []
    in_fence = False
    in_comment = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = balanced and not in_fence
            out.append(("", in_fence))
            continue
        if in_comment:
            if "-->" not in line:
                out.append(("", in_fence))
                continue
            in_comment = False
            line = line.split("-->", 1)[1]
        while "<!--" in line:
            if "-->" in line:
                line = re.sub(r"<!--.*?-->", " ", line, count=1)
            else:
                line = line.split("<!--", 1)[0]
                in_comment = True
        out.append((line, in_fence))
    return out


def strip_frontmatter(text: str) -> tuple[str, int]:
    """Return the body and the number of lines removed, so line numbers stay true."""
    if not text.startswith("---"):
        return text, 0
    parts = text.split("\n")
    for index in range(1, len(parts)):
        if parts[index].strip() == "---":
            return "\n".join(parts[index + 1 :]), index + 1
    return text, 0


def _name_alternation(catalog: set[str]) -> str:
    """Alternation matching hyphenated names case-INsensitively.

    Headings are routinely title-cased (`## PR-Review`) and a case-sensitive
    matcher sees nothing there. Hyphenated names are safe to fold because no
    ordinary English phrase looks like `pr-review`.

    The three catalog names with no hyphen -- graphify, help, remotion -- stay
    case-sensitive: `help` is an ordinary word, and folding it would fire on
    every sentence starting with "Help". A gate that cries wolf gets switched
    off, which costs more than the references it would have found.
    """
    ordered = sorted(catalog, key=len, reverse=True)
    folded = [re.escape(n) for n in ordered if "-" in n]
    exact = [re.escape(n) for n in ordered if "-" not in n]
    parts = []
    if folded:
        parts.append("(?i:" + "|".join(folded) + ")")
    if exact:
        parts.append("|".join(exact))
    return "|".join(parts)


def classify_line(line: str, source: str, catalog: set[str]) -> list[tuple[str, str]]:
    """Return (kind, target) pairs for one line.

    Masking order matters: each class is consumed before the next runs, so a
    single occurrence is never counted twice. The remediation forms are masked
    first and therefore can never be reported.
    """
    if not catalog:
        return []
    alt = _name_alternation(catalog)
    found: list[tuple[str, str]] = []

    # The remediation token. Qualified plugin:x references need no mask -- every
    # pattern below excludes a name preceded by ':' -- and adding one was dead
    # code that survived a mutation test, which is how it was caught.
    line = re.sub(r"\{\{skill:(?:" + alt + r")\}\}", MASK, line)

    # Relative file links. Reported separately: they are paths, not commands,
    # and they survive the cutover whenever source and target share a bundle.
    for match in re.finditer(r"\.\./(" + alt + r")/", line):
        if match.group(1).lower() != source.lower():
            found.append(("relative", match.group(1)))
    line = re.sub(r"\.\./(?:" + alt + r")/", MASK, line)

    # Slash-form. The lookbehind rejects path segments (skills/x/SKILL.md) and
    # the lookahead rejects a name that is itself a directory component.
    for match in re.finditer(
        r"(?<![A-Za-z0-9_:/\-.])/(" + alt + r")(?![A-Za-z0-9_\-/])", line
    ):
        if match.group(1).lower() != source.lower():
            found.append(("slash", match.group(1)))
    line = re.sub(
        r"(?<![A-Za-z0-9_:/\-.])/(?:" + alt + r")(?![A-Za-z0-9_\-/])", MASK, line
    )

    # Bare names, in any markup a skill body actually uses to name a skill:
    # `code span`, **bold**, _italic_, [link](target), <angle>. Both tiers use
    # the SAME pattern -- an earlier version matched bold only on dispatch
    # lines, so the identical form was blocking on one line and invisible on
    # the next. Only the CONSEQUENCE differs: a dispatch verb on the line means
    # the reference is executed, so it blocks; otherwise it is prose a reader
    # is told to type, so it warns and ratchets.
    kind = "dispatch" if DISPATCH_VERBS.search(line) else "prose"
    # `_` is deliberately NOT a word char here: markdown italic delimits with
    # it (`_pr-review_`), so treating it as part of an identifier hid that form.
    pattern = r"(?<![/:A-Za-z0-9.-])(" + alt + r")(?![A-Za-z0-9/.-])"
    for match in re.finditer(pattern, line):
        if match.group(1).lower() != source.lower():
            found.append((kind, match.group(1)))
    return found


def scan_file(path: Path, source: str, catalog: set[str], report: Report) -> None:
    """Append every hit in one file to the report. An unreadable file exits 2
    rather than being skipped: a file the gate could not read is not a file the
    gate has cleared."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        err(f"cannot read {path}: {exc}")
        raise SystemExit(2) from exc

    body, offset = strip_frontmatter(text)
    for index, (line, fenced) in enumerate(masked_lines(body), start=offset + 1):
        for kind, target in classify_line(line, source, catalog):
            # A fenced example is a reference a reader may copy, not a dispatch
            # the model executes. Counted, never blocking.
            if fenced and kind in ("slash", "dispatch"):
                kind = "prose"
            hit = Hit(source, target, kind, str(path), index, line.strip()[:120])
            if kind in ("slash", "dispatch"):
                report.blocking.append(hit)
            elif kind == "relative":
                report.relative.append(hit)
            else:
                report.warning.append(hit)


def scan(roots: list[Path]) -> Report:
    """Walk every *.md under every skill dir in every root. Sidecars count:
    references/ and prompts/ ship inside the plugin and break identically.
    A missing root exits 2 -- scanning nothing must never look clean."""
    catalog = build_catalog(roots)
    report = Report()
    for root in roots:
        if not root.is_dir():
            err(f"root does not exist: {root}")
            raise SystemExit(2)
        for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for md in sorted(skill_dir.rglob("*.md")):
                scan_file(md, skill_dir.name, catalog, report)
    return report


def read_baseline(path: Path | None) -> tuple[int | None, int, set[str] | None]:
    """Return (warning ceiling, blocking ceiling, pinned blocking sites).

    `blocking_sites` pins WHICH references are tolerated, not merely how many.
    A count-only ratchet cannot see a swap -- remove one blocking reference,
    add a different one, and the total is unchanged while the tree has gained a
    brand new silent-failure site. Omit the key and the count alone applies, so
    a baseline written before site-pinning keeps working.

    The blocking ceiling defaults to 0, so omitting it keeps the strict posture:
    any blocking reference fails. It exists because wiring this gate into CI
    while pre-existing blocking references sat in the tree turned every PR red
    for a condition the PR did not cause -- the same ratchet shape
    constitution_baseline.json already uses. Any increase still fails.

    A malformed baseline exits 2 rather than defaulting to unlimited: a corrupt
    ratchet file must not silently become a passing gate.
    """
    if path is None:
        return None, 0, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sites = data.get("blocking_sites")
        return (
            int(data["warning_total"]),
            int(data.get("blocking_total", 0)),
            set(sites) if isinstance(sites, list) else None,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        err(f"unreadable baseline {path}: {exc}")
        raise SystemExit(2) from exc


def check_registry(path: Path, catalog: set[str]) -> bool:
    """True when the committed expected_total equals the catalog on disk.

    The catalog is derived from directory names, so it cannot drift from the
    tree -- but that also means it cannot NOTICE the tree losing a skill. The
    committed integer is the only party to the comparison that the move cannot
    edit, which is exactly why the plan requires it to be exogenous.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        err(f"unreadable registry {path}: {exc}")
        raise SystemExit(2) from exc
    match = re.search(r"^expected_total:\s*(\d+)", text, re.MULTILINE)
    if not match:
        err(f"registry {path} declares no expected_total")
        raise SystemExit(2)
    expected = int(match.group(1))
    ok = True
    if expected != len(catalog):
        err(
            f"registry expected_total is {expected} but {len(catalog)} skills are "
            "on disk - a skill was added or lost without updating the registry"
        )
        ok = False

    # T1.6's deferred half. Every skill needs exactly one bundle: an unassigned
    # skill ships nowhere, and a doubly-assigned one installs twice. Neither is
    # visible to a total, which is why both directions are asserted rather than
    # a count compared.
    assigned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and line.startswith("    "):
            assigned.append(stripped[2:].strip())
    if assigned:
        seen = set(assigned)
        duplicated = sorted({n for n in seen if assigned.count(n) > 1})
        for name in sorted(catalog - seen):
            err(f"skill has no bundle in the registry: {name}")
            ok = False
        for name in sorted(seen - catalog):
            err(f"registry assigns a bundle to a skill that is not on disk: {name}")
            ok = False
        for name in duplicated:
            err(f"skill is assigned to more than one bundle: {name}")
            ok = False
    return ok


def default_roots(repo: Path) -> list[Path]:
    """Where the skills actually live, source-first.

    `.apm/skills` became a GENERATED, gitignored mirror in T3.3. Reporting hits
    there sends whoever reads this output to edit files the next
    generate_skill_mirror.sh run destroys -- a fix that passes review, passes
    the gate on the spot, and is gone by the next rebuild. So the plugin trees
    win when they exist, and the mirror remains the fallback for a checkout
    from before the move.
    """
    plugin_skills = sorted(
        d for d in repo.glob("plugins/*/skills") if d.is_dir()
    )
    return plugin_skills or [repo / ".apm" / "skills"]


def parse_args(argv: list[str]) -> tuple[list[Path], Path | None, Path | None, bool]:
    """Return (roots, baseline, registry, as_json). Exits 2 on an unknown or
    incomplete flag rather than silently ignoring it -- a typo'd --roots that
    fell through to the default would scan the wrong tree and report a
    confident clean."""
    roots_arg, baseline, registry, as_json = None, None, None, False
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--json":
            as_json = True
        elif token == "--roots" and index + 1 < len(argv):
            index += 1
            roots_arg = argv[index]
        elif token == "--baseline" and index + 1 < len(argv):
            index += 1
            baseline = Path(argv[index])
        elif token == "--registry" and index + 1 < len(argv):
            index += 1
            registry = Path(argv[index])
        else:
            err(f"unknown or incomplete argument: {token}")
            raise SystemExit(2)
        index += 1
    if roots_arg is None:
        roots = default_roots(Path(__file__).resolve().parents[3])
    else:
        roots = [Path(p) for p in roots_arg.split(":") if p]
    return roots, baseline, registry, as_json


def report_text(report: Report, limit: int = 20) -> None:
    """Print blocking hits with file:line, capped, then always print the three
    totals. The cap truncates the list but never the counts."""
    for hit in report.blocking[:limit]:
        rel = hit.file
        print(f"BLOCKING {hit.kind:8} {rel}:{hit.line}  {hit.source} -> {hit.target}")
    if len(report.blocking) > limit:
        print(f"... and {len(report.blocking) - limit} more")
    print(
        f"blocking={len(report.blocking)} warning={len(report.warning)} "
        f"relative={len(report.relative)}"
    )


def main(argv: list[str]) -> int:
    """Exit 0 clean, 1 if any blocking reference exists or warnings exceed the
    baseline, 2 on usage or unreadable input. Never 0 with findings."""
    if "--help" in argv or "-h" in argv:
        print(USAGE, end="")
        return 0

    roots, baseline_path, registry_path, as_json = parse_args(argv)
    report = scan(roots)
    baseline, blocking_ceiling, pinned = read_baseline(baseline_path)

    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        report_text(report)

    status = 0
    if registry_path is not None and not check_registry(
        registry_path, build_catalog(roots)
    ):
        status = 1
    if pinned is not None:
        seen = {f"{h.source} -> {h.target}" for h in report.blocking}
        for site in sorted(seen - pinned):
            err(f"new blocking cross-skill reference not in the baseline: {site}")
            status = 1
    if len(report.blocking) > blocking_ceiling:
        err(
            f"{len(report.blocking)} blocking cross-skill reference(s) exceed the "
            f"ceiling of {blocking_ceiling}: these stop resolving once skills are "
            "plugin-scoped, and fail silently"
        )
        status = 1
    elif report.blocking and len(report.blocking) < blocking_ceiling:
        err(
            f"{len(report.blocking)} blocking reference(s) against a ceiling of "
            f"{blocking_ceiling}: lower blocking_total to {len(report.blocking)}. "
            "A ratchet nobody tightens sits at its loosest setting forever."
        )
    elif report.blocking:
        err(
            f"{len(report.blocking)} blocking cross-skill reference(s) held at the "
            f"ratchet ceiling of {blocking_ceiling} - remediate, never raise"
        )
    if baseline is not None and len(report.warning) < baseline:
        err(
            f"{len(report.warning)} prose reference(s) against a ceiling of "
            f"{baseline}: lower warning_total to {len(report.warning)}."
        )
    if baseline is not None and len(report.warning) > baseline:
        err(
            f"warning ratchet: {len(report.warning)} prose references exceed "
            f"baseline {baseline}; lower the count or update the baseline deliberately"
        )
        status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
