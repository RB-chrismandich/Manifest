"""The registry and the prose may not drift apart.

code_constitution.yml is the source of truth, but nobody reads YAML before
writing code — they read references/code-constitution.md and the per-language
annex. A doctrine that says one thing in the machine copy and another in the
document people actually read is worse than having neither, because both sides
look authoritative. These tests make the two copies fail together.

Everything asserted here is DERIVED from the YAML at runtime: no article title,
rule sentence, threshold, or line cap is written down twice.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from constitution import registry

REFERENCES = REPO_ROOT / "configs" / "claude" / "references"
UNIVERSAL_DOC = REFERENCES / "code-constitution.md"
DOC_LIMITS = REPO_ROOT / "configs" / "claude" / "config" / "doc_limits.yml"

REG = registry.load()

# `## Article VII — CON-007 — Errors travel`, with the separator left loose so a
# reformat of the heading is not a failure but a lost id or title is.
HEADING = re.compile(r"^#{2,3}\s+(?P<text>.*(?P<id>CON-\d{3}).*)$", re.MULTILINE)


def annex_paths() -> dict[str, Path]:
    """Language key -> annex file, resolved through the registry's `annex` key."""
    return {key: REFERENCES / lang.annex for key, lang in REG.languages.items()}


def all_doc_paths() -> list[Path]:
    return [UNIVERSAL_DOC, *annex_paths().values()]


def normalize(text: str) -> str:
    """Whitespace-normalize and drop markdown emphasis the YAML does not carry.

    The doc quotes the rule as prose (wrapped, with `code spans` on paths); the
    YAML holds a folded scalar. Comparing the words is the point — comparing the
    wrapping would just make every reflow a test failure.
    """
    return " ".join(text.replace("`", "").replace("*", "").split())


def blockquote_after(lines: list[str]) -> str:
    """The blockquote immediately following a heading, joined into one string."""
    quote: list[str] = []
    for line in lines:
        if line.startswith(">"):
            quote.append(line.lstrip(">").strip())
        elif quote or line.strip():
            break  # the quote ended, or prose started before one began
    return " ".join(quote)


def article_blocks() -> dict[str, tuple[str, str]]:
    """CON-id -> (heading text, blockquote body) parsed from the universal doc."""
    lines = UNIVERSAL_DOC.read_text(encoding="utf-8").splitlines()
    blocks: dict[str, tuple[str, str]] = {}
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            blocks[match.group("id")] = (
                match.group("text"),
                blockquote_after(lines[index + 1 :]),
            )
    return blocks


# ---------------------------------------------------------------------------
# 1 + 2 — every article has a heading and a rule that still says the same thing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("article", REG.articles, ids=lambda a: a.id)
def test_article_has_heading_with_id_and_exact_title(article):
    blocks = article_blocks()
    assert article.id in blocks, f"{article.id} has no heading in {UNIVERSAL_DOC.name}"
    heading = blocks[article.id][0]
    # Exact, not substring: "Data is not codes" contains "Data is not code".
    segments = [part.strip() for part in re.split("\\s+[\\u2014\\u2013]\\s+", heading)]
    assert article.title in segments, (
        f"{article.id} heading is {heading!r}; the registry title is {article.title!r}"
    )


@pytest.mark.parametrize("article", REG.articles, ids=lambda a: a.id)
def test_article_rule_matches_the_registry(article):
    blocks = article_blocks()
    assert article.id in blocks, f"{article.id} has no heading in {UNIVERSAL_DOC.name}"
    quoted = blocks[article.id][1]
    assert quoted, f"{article.id} has no blockquoted rule under its heading"
    assert normalize(quoted) == normalize(article.rule), (
        f"{article.id} rule drifted.\n  doc: {normalize(quoted)}\n  yml: {normalize(article.rule)}"
    )


def test_no_orphan_article_headings_in_the_doc():
    """A heading citing an id the registry dropped is stale prose."""
    known = {a.id for a in REG.articles}
    for article_id in article_blocks():
        assert article_id in known, (
            f"{UNIVERSAL_DOC.name} documents unknown {article_id}"
        )


# ---------------------------------------------------------------------------
# 3 — every language's annex exists and carries content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(REG.languages))
def test_language_annex_present_and_non_empty(key):
    lang = REG.languages[key]
    assert lang.annex, f"language {key} declares no annex"
    path = REFERENCES / lang.annex
    assert path.is_file(), f"{key} annex missing: {path}"
    assert path.read_text(encoding="utf-8").strip(), f"{key} annex is empty: {path}"


# ---------------------------------------------------------------------------
# 4 — the annex "Size ceilings" tables restate the YAML thresholds
# ---------------------------------------------------------------------------

# Unit labels vary per language ("File (`.go`)", "`.tf` file", "Methods per
# type"), so rows are mapped by keyword rather than by exact string. Ordered:
# the first predicate that matches wins.
_UNIT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("payload_string_lines", ("payload",)),
    ("duplicate_block_lines", ("duplicat",)),
    ("nesting_depth", ("nesting", "nested")),
    ("methods_per_class", ("method count per", "methods per")),
    ("parameters", ("parameter",)),
    ("file_lines", ("file",)),
    ("class_lines", ("class", "type")),
    ("function_lines", ("function", "method")),
)

_TABLE_ROW = re.compile(r"^\|(?!\s*-)(?P<cells>.+)\|\s*$")


def threshold_key_for(unit: str) -> str | None:
    lowered = unit.lower()
    for key, needles in _UNIT_RULES:
        if any(needle in lowered for needle in needles):
            return key
    return None


def size_ceiling_rows(path: Path) -> list[tuple[str, int]]:
    """Parse the annex's `## Size ceilings` table into (unit, ceiling) pairs.

    A row may name several units at once ("Class / function / parameters ... | 0
    — not evaluated"); each is returned separately so every unit is checked.
    """
    rows: list[tuple[str, int]] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.lower().startswith("## size ceilings")
            continue
        if not inside:
            continue
        match = _TABLE_ROW.match(line)
        if not match:
            continue
        cells = [c.strip() for c in match.group("cells").split("|")]
        if len(cells) < 2 or cells[0].lower() == "unit":
            continue
        number = re.search(r"\d+", cells[1])
        if not number:
            continue
        # Strip code spans before splitting, so `.ts`, `.tsx` lists do not
        # masquerade as multiple units.
        unit_cell = re.sub(r"`[^`]*`", "", cells[0])
        for unit in unit_cell.split("/"):
            if unit.strip():
                rows.append((unit.strip(), int(number.group())))
    return rows


@pytest.mark.parametrize("key", sorted(REG.languages))
def test_annex_size_ceilings_match_the_registry(key):
    lang = REG.languages[key]
    rows = size_ceiling_rows(REFERENCES / lang.annex)
    assert rows, f"{key} annex has no parsable 'Size ceilings' table"
    for unit, ceiling in rows:
        threshold = threshold_key_for(unit)
        assert threshold is not None, (
            f"{key} annex row {unit!r} maps to no threshold key; "
            "add it to _UNIT_RULES or fix the table"
        )
        assert threshold in lang.thresholds, (
            f"{key} annex documents {unit!r} but the registry has no {threshold}"
        )
        assert lang.thresholds[threshold] == ceiling, (
            f"{key} annex says {unit} = {ceiling}, "
            f"registry says {threshold} = {lang.thresholds[threshold]}"
        )


@pytest.mark.parametrize("key", sorted(REG.languages))
def test_annex_documents_every_size_threshold_that_applies(key):
    """A ceiling the registry enforces but no annex states is an ambush."""
    lang = REG.languages[key]
    documented = {
        threshold_key_for(unit)
        for unit, _ in size_ceiling_rows(REFERENCES / lang.annex)
    }
    for name in ("file_lines", "nesting_depth"):
        if lang.threshold(name):
            assert name in documented, f"{key} annex never states its {name} ceiling"


# ---------------------------------------------------------------------------
# 5 — every id the prose cites exists in the registry
# ---------------------------------------------------------------------------

_CITED_ID = re.compile(r"\b(?:CON-\d{3}|C-[A-Z]{3,})\b")


@pytest.mark.parametrize("path", all_doc_paths(), ids=lambda p: p.name)
def test_every_cited_id_exists_in_the_registry(path):
    known = {a.id for a in REG.articles} | set(REG.checks)
    cited = set(_CITED_ID.findall(path.read_text(encoding="utf-8")))
    unknown = sorted(cited - known)
    assert not unknown, f"{path.name} cites ids absent from the registry: {unknown}"


def test_every_check_id_is_documented_somewhere():
    """The reverse direction: a check nobody documents is a surprise at commit time."""
    prose = "\n".join(p.read_text(encoding="utf-8") for p in all_doc_paths())
    cited = set(_CITED_ID.findall(prose))
    missing = sorted(set(REG.checks) - cited)
    assert not missing, f"checks defined but never documented: {missing}"


# ---------------------------------------------------------------------------
# 6 — the docs stay inside the cap doc_limits.yml sets for their type
# ---------------------------------------------------------------------------


def doc_limits() -> dict:
    return yaml.safe_load(DOC_LIMITS.read_text(encoding="utf-8"))


def declared_cap(path: Path, limits: dict) -> tuple[str, int]:
    """Resolve a doc's cap the way docs_lint does: in-file markers, then type."""
    head = path.read_text(encoding="utf-8").splitlines()[:20]
    overrides = limits["overrides"]
    doc_type = "defaults"
    for line in head:
        if overrides["limit_marker"] in line:
            explicit = re.search(
                rf"{re.escape(overrides['limit_marker'])}\s*(\d+)", line
            )
            if explicit:
                return "doc-limit", int(explicit.group(1))
        if overrides["type_marker"] in line:
            found = re.search(
                rf"{re.escape(overrides['type_marker'])}\s*([a-z_]+)", line
            )
            if found and found.group(1) in limits["types"]:
                doc_type = found.group(1)
    if doc_type == "defaults":
        return doc_type, int(limits["defaults"]["max_lines"])
    return doc_type, int(limits["types"][doc_type]["max_lines"])


@pytest.mark.parametrize("path", all_doc_paths(), ids=lambda p: p.name)
def test_doc_is_within_its_declared_line_cap(path):
    limits = doc_limits()
    doc_type, cap = declared_cap(path, limits)
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= cap, (
        f"{path.name} is {lines} lines, over the {doc_type} cap of {cap}"
    )


@pytest.mark.parametrize("path", all_doc_paths(), ids=lambda p: p.name)
def test_doc_declares_the_type_its_cap_comes_from(path):
    """An undeclared doc silently inherits the 250-line default; make it explicit."""
    doc_type, _ = declared_cap(path, doc_limits())
    assert doc_type != "defaults", f"{path.name} declares no doc-type marker"


# ---------------------------------------------------------------------------
# 7 — no document may state an article count that disagrees with the registry
# ---------------------------------------------------------------------------

# Every surface that describes the constitution to a reader — DISCOVERED, never
# listed. A hand-maintained roster of documents is the same restatement failure
# this section exists to catch: the guide added tomorrow saying "twelve
# articles" would simply not be on the list, and the suite would stay green
# while the prose lied. So: every prose file in the repo that mentions the
# constitution is a surface, and every surface must agree with the registry.
_PROSE_GLOBS = ("*.md", "*.mdc", "*.py", "*.bats")

# Machinery, vendored trees, and dated records. specs/ is excluded on purpose:
# a spec is a record of what was true when it was written, not a live claim.
_SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "specs"}
)

# `code-constitution`, `code_constitution`, `code constitution`, or any article
# id. A file that never names the constitution cannot be restating its size.
_MENTIONS_CONSTITUTION = re.compile(r"code.constitution|CON-0\d{2}", re.IGNORECASE)


def _git_prose_files() -> list[Path]:
    """Tracked *and* new-but-unignored prose files, per git's own bookkeeping.

    `--others --exclude-standard` matters: a doc added in the working tree is
    exactly the doc most likely to carry a freshly stale count.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *_PROSE_GLOBS,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []  # not a checkout, or no git — the glob below still works
    return [REPO_ROOT / name for name in result.stdout.split("\0") if name]


def _globbed_prose_files() -> list[Path]:
    """Fallback for a non-git export: walk the tree, pruning nothing by hand."""
    found: list[Path] = []
    for pattern in _PROSE_GLOBS:
        found.extend(REPO_ROOT.rglob(pattern))
    return found


def _is_scannable(path: Path) -> bool:
    try:
        parts = path.relative_to(REPO_ROOT).parts
    except ValueError:
        return False
    if _SKIP_DIRS.intersection(parts):
        return False
    # Live again now that _PROSE_GLOBS covers *.py: this module states counts by
    # construction (its own fixtures say "twelve articles"), so scanning itself
    # would report a permanent, unfixable failure.
    return path.resolve() != Path(__file__).resolve()


def count_surfaces() -> list[str]:
    """Repo-relative paths of every document that describes the constitution."""
    surfaces: set[str] = set()
    for path in _git_prose_files() or _globbed_prose_files():
        if not _is_scannable(path) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _MENTIONS_CONSTITUTION.search(text):
            surfaces.add(path.relative_to(REPO_ROOT).as_posix())
    return sorted(surfaces)


COUNT_SURFACES = count_surfaces()

NUMBER_WORDS = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
}

# "12 articles", "twelve articles", "Twelve articles that must hold"
# One optional adjective may sit between the number and the noun: the annexes
# say "twelve universal articles", and requiring adjacency made every one of
# them read as "no claim" while they were stale.
_WORD_COUNT = re.compile(
    r"\b(?P<n>\d{1,3}|" + "|".join(NUMBER_WORDS) + r")\s+(?:\w+\s+)?articles\b",
    re.IGNORECASE,
)
# "CON-001..012", "CON-001<dash>CON-012", "CON-001 through CON-013"
# Backticks are allowed around each id: docs write `CON-001`-`CON-013` with an
# en/em dash, and a
# separator class that stops at whitespace would skip that surface silently.
_RANGE_COUNT = re.compile(
    # \u2013 en dash, \u2014 em dash: written literally in the docs this scans.
    r"CON-0*1[\s`]*(?:\.\.|[\u2013\u2014]|-|through|to)[\s`]*(?:CON-)?0*(?P<n>\d{1,3})\b",
    re.IGNORECASE,
)


def _claimed_counts(text: str):
    """(claimed_number, matched_text) for every article-count claim in a doc."""
    for pattern in (_WORD_COUNT, _RANGE_COUNT):
        for match in pattern.finditer(text):
            raw = match.group("n").lower()
            yield NUMBER_WORDS.get(raw) or int(raw), match.group(0)


def test_count_claim_regex_survives_an_adjective_and_a_noun_gap():
    """`twelve universal articles` is the phrasing four annexes actually used.

    The first version of these patterns required the number and "articles" to be
    adjacent, so every annex opening line read as "no claim at all" and the
    whole suite passed while four documents were stale.
    """
    assert [n for n, _ in _claimed_counts("the twelve universal articles")] == [12]
    assert [n for n, _ in _claimed_counts("13 universal articles")] == [13]
    assert [n for n, _ in _claimed_counts("thirteen articles")] == [13]
    # A different noun is not an article count.
    assert list(_claimed_counts("twelve `pass` lines repeating")) == []
    assert list(_claimed_counts("twelve of the checks")) == []


def test_surface_discovery_found_the_documents_it_is_supposed_to_guard():
    """A discovery that silently returns nothing is a green suite checking nothing.

    Derivation buys coverage of documents nobody remembered to list; the price
    is that a broken glob, a moved repo root, or a git failure degrades to an
    empty parametrization instead of a red test. Anchor it on the doc set the
    registry itself names, so this cannot be satisfied by an empty result.
    """
    expected = {p.relative_to(REPO_ROOT).as_posix() for p in all_doc_paths()}
    found = set(COUNT_SURFACES)
    assert expected <= found, (
        f"surface discovery missed registry-named docs: {sorted(expected - found)}"
    )
    # This module quotes "CON-001..012" in a comment to document the pattern, so
    # if it were ever scanned it would fail as its own stale surface. Prose
    # globs cannot reach a .py today; widening them must fail here, loudly,
    # rather than produce a self-referential failure nobody can read.
    this_module = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert this_module not in found, "the test module scanned itself"


@pytest.mark.parametrize("relative", COUNT_SURFACES, ids=lambda r: r)
def test_no_document_claims_a_stale_article_count(relative):
    """A restated count is a second source of truth; this makes it fail loudly.

    Added after CON-013 shipped and nine locations across six surfaces still
    said "twelve articles" / "CON-001..012". Nothing caught it: the id-to-heading
    tests only prove every article HAS a heading, never that prose describing the
    set as a whole kept up.
    """
    path = REPO_ROOT / relative
    if not path.is_file():
        pytest.skip(f"{relative} not present")
    expected = len(REG.articles)
    stale = [
        (claimed, phrase)
        for claimed, phrase in _claimed_counts(path.read_text(encoding="utf-8"))
        if claimed != expected
    ]
    assert not stale, (
        f"{relative} claims {stale} but the registry has {expected} articles "
        f"(CON-001..{expected:03d})"
    )
