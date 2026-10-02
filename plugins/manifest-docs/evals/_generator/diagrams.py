"""docs-generate-diagrams eval cases."""

import common
import fixtures as F
from common import IN_MERMAID, LE, Case, f, fired, llm, not_fired, regex

SKILL = "docs-generate-diagrams"
PAGE = "docs/ARCHITECTURE_DIAGRAMS.md"
MERMAID5 = r"(?:```mermaid[\s\S]*?){5}"
DIAG_OK = """
Check every Mermaid diagram in the file. (1) Syntax: each declares a diagram type on its first line (flowchart, sequenceDiagram, classDiagram, stateDiagram) and has no unclosed brackets, unclosed subgraphs, or prose lines inside the block. (2) Every internal component shown is a real part of the repo: tally.cli (ingest and report commands), tally.config, tally.ingest, tally.store, tally.report, or their functions. External actors are fine: the user/shell, the CSV input file, tally.toml, the SQLite database file, click. Invented components fail it: Redis, a queue, an API/web server, a cache, a separate database service. (3) Each diagram has at most 20 nodes and a short caption. Pass only if all three hold."""


def _fresh(root):
    common.write_case(
        root,
        "06-diag-fresh",
        {**F.CODE, "README.md": F.good_readme()},
        Case(
            f"Add architecture diagrams for this project in {PAGE}.",
            {
                "has-mermaid": regex(r"```mermaid", f(PAGE)),
                "at-most-4": regex(MERMAID5, f(PAGE), "not_contains"),
                "matches-code": llm(DIAG_OK, f(PAGE)),
                "under-cap": regex(LE(300), f(PAGE), "not_contains", weight=0.5),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _huge(root):
    common.write_case(
        root,
        "07-diag-huge",
        {**F.CODE, PAGE: F.huge_diagrams()},
        Case(
            f"The diagram doc ({PAGE}) is huge and nobody can find anything in it. Sort it out.",
            {
                "no-part-n": regex(r"part-?\d", "files", "not_contains", "i"),
                "outcome": llm(
                    """
From the trace, judge the final docs state. Pass only if: (1) no resulting diagram page holds more than 4 mermaid blocks or 300 lines; (2) the seven near-identical diagrams were consolidated or dropped rather than copied verbatim into new pages; (3) any hub page is navigation only, one line per child; (4) the final reply says which diagrams were dropped/merged and why.""",
                    "trace",
                ),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _stale(root):
    common.write_case(
        root,
        "08-diag-stale",
        {**F.CODE, PAGE: F.stale_diagrams()},
        Case(
            f"Our diagrams in {PAGE} are out of date — we ripped Redis out a while back. Update them to match the code.",
            {
                "redis-gone": regex(r"redis", f(PAGE), "not_contains", "i"),
                "has-mermaid": regex(r"```mermaid", f(PAGE)),
                "sqlite-in-diagram": regex(IN_MERMAID("sqlite"), f(PAGE), flags="i"),
                "matches-code": llm(DIAG_OK, f(PAGE)),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _sequence(root):
    flow = "docs/ingest-flow.md"
    common.write_case(
        root,
        "09-diag-sequence",
        {**F.CODE, "README.md": F.good_readme()},
        Case(
            f"Draw a diagram of how one record gets from `tally ingest` into the database, and put it in {flow}.",
            {
                "has-mermaid": regex(r"```mermaid", f(flow)),
                "call-order": llm(
                    """
The diagram shows this order and nothing invented in between: cli `ingest` command → config.load (db_path) → ingest.run → ingest.read_csv (csv.DictReader) → ingest.normalize (lower-cases event) → store.save → SQLite `events` table INSERT. Omitting config.load or the one-line ingest.run pass-through is fine; wrong order, invented steps (validation service, queue, cache) or missing store.save fail. Syntax must be valid Mermaid.""",
                    f(flow),
                ),
                "one-concept": regex(
                    r"(?:```mermaid[\s\S]*?){3}", f(flow), "not_contains", weight=0.5
                ),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _neg_syntax(root):
    common.write_case(
        root,
        "10-diag-neg-syntax",
        None,
        Case(
            "Quick question: what's the Mermaid syntax for grouping nodes in a subgraph inside a flowchart?",
            {
                "answers": regex(r"subgraph[\s\S]*\bend\b", flags="i"),
                "no-docs-skill": not_fired("docs-"),
                "no-files": regex(r"\S", "files", "not_contains"),
                "correct": llm(
                    "The reply shows a flowchart containing `subgraph <id>[<title>]` (or `subgraph title`) ... `end`, with nodes inside and an edge, in valid Mermaid syntax, and does not claim to have created or edited any file."
                ),
            },
            5,
            120,
            ["Skill", "Read", "Write"],
        ),
    )


def diagrams(root):
    _fresh(root)
    _huge(root)
    _stale(root)
    _sequence(root)
    _neg_syntax(root)
