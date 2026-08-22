#!/usr/bin/env python3
"""Fail when a skill cites a path that does not exist inside its own bundle.

Bundles install independently (spec:
docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md, Phase 1
item 1.4). A skill that cites a sibling bundle's file, a monorepo-only path
(``configs/``, ``tests/``, ``docs/``, ``tools/``, ...), or the
bootstrap-deployed home tree (``~/.claude/references``, ``~/.claude/prompts``)
reads fine in this monorepo and breaks the moment the bundle is installed
alone -- the file simply is not there.

This gate resolves every path-shaped citation found in each skill's own
directory tree (``plugins/<bundle>/skills/<name>/**``) into one of three
confirmable outcomes: bundle-local and present (not a defect), present only
*outside* the citing bundle (``cross-bundle-path``), or unambiguously
bundle-anchored -- via ``$CLAUDE_PLUGIN_ROOT``/``${CLAUDE_PLUGIN_ROOT}`` or a
``../``-relative path that lexically lands inside the bundle -- yet absent
(``missing-bundle-local-target``: a typo'd or deleted file, invisible to a
checker that only ever asked "does this exist somewhere else?"). It also
carries a small registry of filenames historically cited bare, as if the
bundle carried its own copy, when in fact exactly one canonical copy exists
elsewhere in the repository (``sub-agent-dispatch.md``, ``command_config.yml``,
...), reported as ``missing-bundled-reference``.

``$CLAUDE_PLUGIN_ROOT`` and ``${CLAUDE_PLUGIN_ROOT}`` (braced and unbraced --
both are substituted identically by Claude Code) resolve identically here.

It deliberately does NOT flag: relative paths (``../..``) that resolve
outside the bundle but cannot be confirmed to exist anywhere (left alone
rather than guessed at, same as any other unanchored citation); URLs; shell
variables other than ``CLAUDE_PLUGIN_ROOT``; glob patterns; a bare filename
that merely appears in prose with no positive signal that a same-named file
exists anywhere else in the repository; or a machine-generated data file
(see ``_GENERATED_DATA_FILES``) whose path-shaped strings are catalog/ratchet
records, not a skill's own citation. A citation this gate cannot resolve at
all (typo with no bundle anchor, hypothetical example) is left alone rather
than guessed at -- see
``docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md`` §4
Phase 1 item 1.4 for the "known non-defect" cases this design is calibrated
against.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Sibling module (not a package -- tools/ ships no __init__.py); the explicit
# sys.path entry makes the import work both when this file runs directly
# (Python already puts its own directory on sys.path[0]) and when a test
# loads it via importlib.util.spec_from_file_location, which does not.
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
import bundle_link_baseline  # noqa: E402
import check_runtime_source_directives  # noqa: E402

_TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".json", ".py", ".sh"}
_UNSCANNED_DIRS = frozenset({"vendor", "dist", "node_modules", "__pycache__", ".git"})

# Cross-bundle-shared reference filenames with exactly one canonical location
# in the repository, historically cited *bare* (no directory component) as if
# the citing bundle carried its own copy. See spec §1.1's defect table and the
# Phase 1.1 vendoring target list. Extend this list only for a filename that
# is genuinely a single-source shared reference -- a generic project filename
# (README.md, package.json, CLAUDE.md, ...) belongs to the target repository
# a skill operates ON, never to this registry, and must stay unlisted or every
# skill that mentions "your project's README.md" starts failing this gate.
_SHARED_REFERENCE_BASENAMES: tuple[str, ...] = (
    "sub-agent-dispatch.md",
    "command_config.yml",
    "harness-routing.md",
    "antipatterns.md",
    "code-constitution.md",
)

# Machine-generated data files: their path-shaped strings are catalog/ratchet
# records keyed or valued by a filesystem path, not a skill instructing an
# agent to go read that file. Scanning them attributes the "citation" to the
# wrong actor -- the generator, not the skill. Each entry is a real
# generator -> output pairing verified in this repo; extend only for the same
# shape, never to hide a hand-authored SKILL.md/reference citation.
#
# - tools/generate_plugin_views.py writes ``help/catalog/commands.json``, a
#   catalog of every skill's own frontmatter description. token-benchmark's
#   description legitimately mentions "docs/TOKEN_BENCHMARK.md" -- that
#   citation is caught at its true source (the skill's own SKILL.md); the
#   copy here is a duplicate echo, not a second defect.
# - ``constitution_check.py --update-baseline`` writes
#   ``config/constitution_baseline.json``, a ratchet of pre-existing
#   violation counts keyed by the monorepo-era file path they were measured
#   against (".specify/...", "legacy-setup/...", "bundle-runtime/..."),
#   several of which now coincidentally collide with real files under
#   unrelated bundles post-migration.
_GENERATED_DATA_FILES: frozenset[str] = frozenset(
    {
        "manifest-workspace/skills/help/catalog/commands.json",
        "manifest-code-quality/skills/code-audit-constitution/config/"
        "constitution_baseline.json",
    }
)

_PATH_EXTENSIONS = "md|ya?ml|json|py|sh|mjs|js"

# A path-shaped citation: an optional ``$CLAUDE_PLUGIN_ROOT``/
# ``${CLAUDE_PLUGIN_ROOT}``/``..``/``.`` anchor (repeated ``../`` allowed),
# then one or more ``/``-joined segments, ending in a filename with a known
# extension. Requires at least one path separator, so a bare filename never
# matches here (that is the registry check below, deliberately scoped
# narrower). The leading negative lookbehind excludes a start position
# immediately preceded by a word/path/dot/hyphen character, which as a side
# effect keeps this from ever starting a match inside a URL: every interior
# segment of a URL path is preceded by ``/``. The unbraced
# ``\$CLAUDE_PLUGIN_ROOT`` alternative is listed before the bare-word
# alternative so a match starting at the ``$`` wins; if what follows isn't a
# ``/`` (e.g. a *different* variable like ``$CLAUDE_PLUGIN_ROOT_OTHER``) this
# alternative simply fails to complete and the bare-word alternative takes
# over one position later, at the ``C``. The trailing negative lookahead
# rejects a following ``.`` + word-char, not just a bare word-char: without
# that, a real ``foo.md.template`` citation greedily backtracks onto the
# unintended, truncated match ``foo.md`` (".template" isn't a recognized
# extension, so the regex keeps shrinking until it finds ANY recognized one,
# landing mid-filename) -- a genuine sentence-ending "file.md." still
# matches, since nothing word-shaped follows that period.
_PATH_TOKEN_RE = re.compile(
    r"(?<![\w/.-])"
    r"("
    r"(?:\.\./)*"
    r"(?:\.\.|\.|\$\{CLAUDE_PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT|[A-Za-z0-9_-]+)"
    # `..` allowed as an INTERIOR segment too, or an escaping citation is
    # never even tokenised and the containment check above never sees it.
    r"(?:/(?:\.\.|[A-Za-z0-9_-]+))*"
    r"/[A-Za-z0-9_.-]+\.(?:" + _PATH_EXTENSIONS + r")"
    r")"
    r"(?![A-Za-z0-9_]|\.[A-Za-z0-9_])"
)

_BARE_REFERENCE_RE = re.compile(
    r"(?<![\w/.-])("
    + "|".join(re.escape(name) for name in _SHARED_REFERENCE_BASENAMES)
    + r")(?![A-Za-z0-9_])"
)

# ~/.claude/references and ~/.claude/prompts specifically: the two read-on-
# demand trees a skill can plausibly assume are always present in an install.
# ~/.claude/scripts and ~/.claude/config are already covered by
# tools/check_plugin_runtime_paths.py's FORBIDDEN_RUNTIME_PATTERNS.
# ~/.claude/settings.json, ~/.claude/plugins/*, ~/.claude.json etc. are
# legitimate live-install inspection targets a skill like deploy-retire-
# component genuinely needs to name -- not citations of a file the skill
# assumes it ships -- so they are deliberately not matched here.
_HOME_TREE_RE = re.compile(
    r"(?:~|\$HOME|\$\{HOME\})/\.claude/(?:references|prompts)/"
    r"[A-Za-z0-9_./-]+\.(?:" + _PATH_EXTENSIONS + r")"
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    kind: str
    value: str
    message: str

    def as_json(self, root: Path) -> dict[str, Any]:
        item = asdict(self)
        try:
            item["path"] = str(self.path.relative_to(root))
        except ValueError:
            item["path"] = str(self.path)
        return item


@dataclass(frozen=True)
class ScanReport:
    violations: tuple[Violation, ...]


def _line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


@dataclass(frozen=True)
class _FileContext:
    """One file's scan state, shared across the three per-file scanners.

    ``text``/``offset`` are the frontmatter-stripped body and the character
    offset that body starts at in ``raw`` -- callers match against ``text``
    but need line numbers against the original file, hence ``violation()``
    adding ``offset`` back before delegating to ``_line_number``.
    """

    path: Path
    raw: str
    text: str
    offset: int

    def violation(
        self, match_start: int, kind: str, value: str, message: str
    ) -> Violation:
        return Violation(
            self.path,
            _line_number(self.raw, self.offset + match_start),
            kind,
            value,
            message,
        )


def _strip_frontmatter(text: str) -> tuple[str, int]:
    """Return ``(body, offset)`` with a leading ``---`` YAML block removed.

    ``offset`` is the character position the body starts at in ``text``, so a
    caller can add it back to a match position and report the correct line
    number against the original file. Frontmatter (the ``description:``
    field in particular) legitimately names files the skill regenerates or
    documents about itself -- not a citation the skill body depends on -- so
    it is excluded from scanning rather than risking a false positive there.
    """
    if not text.startswith("---\n"):
        return text, 0
    end = text.find("\n---", 4)
    if end == -1:
        return text, 0
    end = text.find("\n", end + 1)
    if end == -1:
        return text, 0
    return text[end + 1 :], end + 1


def _skill_files(bundle_dir: Path) -> list[Path]:
    """Every text file a skill ships: ``SKILL.md`` plus its own directory tree.

    Scoped to ``skills/<name>/**`` rather than the whole bundle -- a stray
    comment in a bundle-root ``runtime/config/*.yml`` file is not something a
    SKILL.md instructs the model to read, and scanning it would misattribute
    the defect to a skill that never cited it.
    """
    skills_root = bundle_dir / "skills"
    if not skills_root.is_dir():
        return []
    files: list[Path] = []
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        for candidate in sorted(skill_dir.rglob("*")):
            if not candidate.is_file() or candidate.suffix not in _TEXT_SUFFIXES:
                continue
            if _UNSCANNED_DIRS & set(candidate.relative_to(skill_dir).parts):
                continue
            if (
                candidate.relative_to(bundle_dir.parent).as_posix()
                in _GENERATED_DATA_FILES
            ):
                continue
            files.append(candidate)
    return files


def _within(path: Path, ancestor: Path) -> bool:
    try:
        path.resolve().relative_to(ancestor.resolve())
        return True
    except ValueError:
        return False


# _resolve_path_citation outcomes. Three are confirmable and drive a
# violation; the fourth (UNRESOLVED) means the checker cannot tell either way
# and leaves the citation alone -- see the module docstring.
_BUNDLE_LOCAL = "bundle-local"  # exists inside the bundle -- not a defect
_OUTSIDE_BUNDLE = "outside-bundle"  # exists only outside the bundle
_BUNDLE_LOCAL_MISSING = "bundle-local-missing"  # bundle-anchored, but absent
_UNRESOLVED = "unresolved"  # cannot confirm either way


_CLAUDE_PLUGIN_ROOT_PREFIXES: tuple[str, ...] = (
    "${CLAUDE_PLUGIN_ROOT}",
    "$CLAUDE_PLUGIN_ROOT",
)


def _bundle_anchor_target(token: str, bundle_dir: Path) -> Path | None:
    """Return the bundle-relative file a ``$CLAUDE_PLUGIN_ROOT`` citation
    names, or ``None`` if ``token`` is not anchored that way.

    Braced and unbraced forms are equivalent -- Claude Code substitutes both
    identically -- so both resolve against the same base, ``bundle_dir``.
    """
    for prefix in _CLAUDE_PLUGIN_ROOT_PREFIXES:
        if token.startswith(prefix):
            return bundle_dir / token[len(prefix) :].lstrip("/")
    return None


def _resolve_path_citation(
    token: str, citing_file: Path, bundle_dir: Path, repo_root: Path
) -> tuple[str, Path | None]:
    """Classify a path-shaped citation; see the outcome constants above.

    ``_OUTSIDE_BUNDLE`` and ``_BUNDLE_LOCAL_MISSING`` always carry the
    resolved target as the second element; ``_BUNDLE_LOCAL`` and
    ``_UNRESOLVED`` always carry ``None``.
    """
    anchored = _bundle_anchor_target(token, bundle_dir)
    if anchored is not None:
        # Plugin-root anchoring does NOT imply containment:
        # `${CLAUDE_PLUGIN_ROOT}/../other-bundle/x.md` is anchored and still
        # escapes, so it must be classified outside-bundle, not local.
        if not _within(anchored, bundle_dir):
            return _OUTSIDE_BUNDLE, anchored.resolve()
        # Contained: absence is confirmable, not an "exists elsewhere?" guess.
        if anchored.is_file():
            return _BUNDLE_LOCAL, None
        return _BUNDLE_LOCAL_MISSING, anchored

    if token.startswith(("./", "../")) or token in (".", ".."):
        target = citing_file.parent / token
        if target.is_file():
            return (
                (_BUNDLE_LOCAL, None)
                if _within(target, bundle_dir)
                else (_OUTSIDE_BUNDLE, target.resolve())
            )
        # Missing. ``../`` is deliberate file-tree navigation -- nobody
        # writes two-plus directory hops by accident -- so a ``../``-rooted
        # token that lexically lands inside this bundle is confirmable: the
        # skill author meant a specific bundle-local file, and it is not
        # there. A bare ``./`` gets no such benefit of the doubt: corpus
        # survey (2026-08-19) shows every real ``./x.ext`` in this repo is
        # either a genuine same-directory citation (handled above, since it
        # exists) or shell-idiom prose/example ("run ./setup.sh",
        # "--spec ./spec.md") naming a script in whatever repo the *reader*
        # runs it against, not a file this bundle ships -- so a missing
        # ``./x`` is left unresolved rather than guessed at.
        if token.startswith("../") and _within(target, bundle_dir):
            return _BUNDLE_LOCAL_MISSING, target.resolve()
        return _UNRESOLVED, None

    for base in (citing_file.parent, bundle_dir):
        if (base / token).is_file():
            return _BUNDLE_LOCAL, None
    candidate = repo_root / token
    if candidate.is_file() and not _within(candidate, bundle_dir):
        return _OUTSIDE_BUNDLE, candidate.resolve()
    return _UNRESOLVED, None


def _path_token_violations(
    ctx: _FileContext, bundle_dir: Path, repo_root: Path
) -> list[Violation]:
    violations: list[Violation] = []
    for match in _PATH_TOKEN_RE.finditer(ctx.text):
        token = match.group(1)
        kind, target = _resolve_path_citation(token, ctx.path, bundle_dir, repo_root)
        if target is None:  # _BUNDLE_LOCAL or _UNRESOLVED -- not a defect
            continue
        try:
            display_target = target.relative_to(repo_root.resolve())
        except ValueError:
            display_target = target
        if kind == _OUTSIDE_BUNDLE:
            violation_kind, message = (
                "cross-bundle-path",
                f"cites {token!r}, which exists only at {display_target} -- "
                f"outside {bundle_dir.name}",
            )
        else:  # _BUNDLE_LOCAL_MISSING
            violation_kind, message = (
                "missing-bundle-local-target",
                f"cites {token!r} as a path inside its own bundle, but "
                f"{display_target} does not exist",
            )
        violations.append(ctx.violation(match.start(1), violation_kind, token, message))
    return violations


def _home_tree_violations(ctx: _FileContext) -> list[Violation]:
    return [
        ctx.violation(
            match.start(),
            "home-tree-path",
            match.group(0),
            f"cites bootstrap-deployed home path {match.group(0)!r}, "
            "absent from a plugin-only install",
        )
        for match in _HOME_TREE_RE.finditer(ctx.text)
    ]


def _bare_reference_violations(ctx: _FileContext, bundle_dir: Path) -> list[Violation]:
    violations: list[Violation] = []
    for match in _BARE_REFERENCE_RE.finditer(ctx.text):
        name = match.group(1)
        if any(bundle_dir.rglob(name)):
            continue
        violations.append(
            ctx.violation(
                match.start(1),
                "missing-bundled-reference",
                name,
                f"cites {name!r} as if bundled, but no file named {name!r} "
                f"exists anywhere under {bundle_dir.name}",
            )
        )
    return violations


def _scan_file(path: Path, bundle_dir: Path, repo_root: Path) -> list[Violation]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    text, offset = _strip_frontmatter(raw) if path.name == "SKILL.md" else (raw, 0)
    ctx = _FileContext(path, raw, text, offset)
    return [
        *_path_token_violations(ctx, bundle_dir, repo_root),
        *_home_tree_violations(ctx),
        *_bare_reference_violations(ctx, bundle_dir),
    ]


def _bundle_dirs(repo_root: Path) -> list[Path]:
    plugins = repo_root / "plugins"
    if not plugins.is_dir():
        return []
    return sorted(
        p for p in plugins.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def _runtime_bin_source_violations(bundle_dir: Path) -> list[Violation]:
    """Script-to-script ``source``/``.`` directives under a bundle's
    ``runtime/bin/**`` (spec §4 Phase 1 item 1.3's own requirement) --
    delegated to a sibling module (CON-002/C-SIZE: this file is already at
    its line ceiling) so a stray script comment never gets scanned by the
    SKILL.md-oriented path-token logic above; see that module's docstring.
    """
    return [
        Violation(path, line, kind, value, message)
        for path, line, kind, value, message in check_runtime_source_directives.scan_bundle(
            bundle_dir
        )
    ]


def scan(repo_root: Path = ROOT) -> ScanReport:
    """Return every bundle-local-link violation under ``repo_root``."""
    repo_root = repo_root.resolve()
    violations: list[Violation] = []
    for bundle_dir in _bundle_dirs(repo_root):
        for file_path in _skill_files(bundle_dir):
            violations.extend(_scan_file(file_path, bundle_dir, repo_root))
        violations.extend(_runtime_bin_source_violations(bundle_dir))
    ordered = tuple(
        sorted(
            violations,
            key=lambda item: (str(item.path), item.line, item.kind, item.value),
        )
    )
    return ScanReport(ordered)


PROG = "check_bundle_link_references.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    # Phase 0 baseline ratchet -- see bundle_link_baseline.py's module docstring.
    parser.add_argument(
        "--no-baseline", action="store_true", help="ignore the baseline"
    )
    parser.add_argument("--update-baseline", action="store_true", help="regenerate it")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    report = scan(args.repo_root)

    if args.update_baseline:
        return bundle_link_baseline.write_update(report.violations, root, prog=PROG)

    result = bundle_link_baseline.apply(
        report.violations, root, no_baseline=args.no_baseline
    )
    return bundle_link_baseline.report(result, root, args.as_json, prog=PROG)


if __name__ == "__main__":
    raise SystemExit(main())
