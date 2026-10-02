"""docs-all eval cases."""

import common
import fixtures as F
from common import IN_MERMAID, LE, TOOLS, Case, exact, f, fired, llm, not_fired, regex
from diagrams import DIAG_OK

SKILL = "docs-all"
ALL_TOOLS = [*TOOLS, "Agent"]

ALL_REPORT = """
The final reply is a measured refresh report that (1) states the order the README, diagram, and docs-audit work ran in, with a reason; (2) gives each of the three parts an outcome (success/failed/skipped with the error); (3) shows before → after numbers for over-cap docs or line totals; (4) names every doc still over cap, or states none remain. Fail if any of the four is missing."""

MERMAID_WRITE = (
    r'"file_path":"[^"]*/docs/[^"]*\.md","content":"(?:[^"\\]|\\.)*```mermaid'
    r'|"file_path":"[^"]*/docs/[^"]*\.md",(?:"old_string":"(?:[^"\\]|\\.)*",)?"new_string":"(?:[^"\\]|\\.)*```mermaid'
    r'|"command":"(?:[^"\\]|\\.)*docs/[^"\\\s]*\.md(?:[^"\\]|\\.)*```mermaid'
    r'|"command":"(?:[^"\\]|\\.)*```mermaid(?:[^"\\]|\\.)*docs/[^"\\\s]*\.md'
)
CONFIG_FACTS = r"^(?=[\s\S]*threshold[^\n]*\b5\b)(?=[\s\S]*tally\.db)(?=[\s\S]*window_minutes[^\n]*\b60\b)"
DOCS_REACHABLE = (
    r"\]\((?:\./)?docs/(?:README|index)\.md\)"
    r"|^(?=[\s\S]*\]\((?:\./)?docs/GETTING_STARTED\.md[)#])(?=[\s\S]*\]\((?:\./)?docs/CONFIGURATION\.md[)#])"
)
TS_FLUFF = r"it is important to note|simply|needless to say|please note that|basically|obviously|in this document we will"

MESSY = {
    **F.CODE,
    "README.md": F.bloated_readme(),
    **F.SMALL,
    "docs/TROUBLESHOOTING.md": F.troubleshooting(),
    "docs/CONFIGURATION.md": F.config_ref(),
}
COMMON_GRADERS = {
    "readme-under-cap": regex(LE(200), f("README.md"), "not_contains"),
    "diagrams-created": regex(MERMAID_WRITE, "trace"),
    "config-under-cap": regex(LE(400), f("docs/CONFIGURATION.md"), "not_contains"),
    "config-facts-kept": regex(CONFIG_FACTS, f("docs/CONFIGURATION.md"), flags="i"),
    "troubleshooting-fluff-gone": regex(
        TS_FLUFF, f("docs/TROUBLESHOOTING.md"), "not_contains", "i", weight=0.5
    ),
    "docs-reachable": regex(DOCS_REACHABLE, f("README.md")),
    "report": llm(ALL_REPORT),
    "skill-fired": fired(SKILL),
}


def _refresh(root):
    common.write_case(
        root,
        "16-all-refresh",
        MESSY,
        Case("Refresh all the docs in this repo.", COMMON_GRADERS, 60, 1500, ALL_TOOLS),
    )


def _bad_order(root):
    common.write_case(
        root,
        "17-all-bad-order",
        MESSY,
        Case(
            "Refresh all the docs. Run them in this order: --order docs-improve,docs-improve-readme,docs-generate-diagrams",
            {
                "warns-order": llm(
                    "The reply warns that the requested order puts the docs audit (docs-improve) first although it depends on the README and diagram updates — i.e. it flags the dependency violation — and states the order it actually used. Running the requested order unchanged, with that warning, is correct per the skill; silently running it with no warning fails, and silently reordering without saying so also fails."
                ),
                "readme-under-cap": COMMON_GRADERS["readme-under-cap"],
                "diagrams-created": COMMON_GRADERS["diagrams-created"],
                **{
                    k: COMMON_GRADERS[k]
                    for k in (
                        "config-under-cap",
                        "config-facts-kept",
                        "troubleshooting-fluff-gone",
                        "docs-reachable",
                    )
                },
                "report": llm(ALL_REPORT, weight=0.5),
                "skill-fired": fired(SKILL),
            },
            60,
            1500,
            ALL_TOOLS,
        ),
    )


def _refactor(root):
    refactor = {k: v for k, v in F.CODE.items() if k != "tally/ingest.py"}
    refactor.update(F.SPLIT_INGEST)
    refactor.update(
        {
            "README.md": F.good_readme(),
            "docs/ARCHITECTURE_DIAGRAMS.md": F.split_stale_diagrams(),
            **F.SMALL,
        }
    )
    common.write_case(
        root,
        "18-all-refactor",
        refactor,
        Case(
            "We just split ingest into a package with separate reader and normalize modules. Update all the docs to match.",
            {
                "diagram-updated": regex(
                    r"ingest\.py", f("docs/ARCHITECTURE_DIAGRAMS.md"), "not_contains"
                ),
                "diagram-has-reader": regex(
                    IN_MERMAID("reader"),
                    f("docs/ARCHITECTURE_DIAGRAMS.md"),
                    flags="i",
                ),
                "diagram-has-normalize": regex(
                    IN_MERMAID("normalize"),
                    f("docs/ARCHITECTURE_DIAGRAMS.md"),
                    flags="i",
                ),
                "diagram-accurate": llm(
                    DIAG_OK
                    + " Also: the ingest path is shown as the tally.ingest package with reader (read_csv) and normalize as separate nodes, and no node for a single tally/ingest.py file. Either shape is accurate: a data-flow chain (reader → normalize → store) or a call graph where the package __init__ / ingest.run calls reader, normalize, and store. Fail only if the modules are wired in a way the code contradicts (e.g. store calling normalize, reader writing to the store).",
                    f("docs/ARCHITECTURE_DIAGRAMS.md"),
                ),
                "report": llm(ALL_REPORT, weight=0.5),
                "skill-fired": fired(SKILL),
            },
            60,
            1500,
            ALL_TOOLS,
        ),
    )


def _casual(root):
    common.write_case(
        root,
        "19-all-casual",
        MESSY,
        Case(
            "honestly the docs are a mess across the board — readme, diagrams, the docs folder. update everything at once",
            {**COMMON_GRADERS},
            60,
            1500,
            ALL_TOOLS,
        ),
    )


def _neg_readme_only(root):
    narrow = F.good_readme(install="python setup.py install")
    common.write_case(
        root,
        "20-all-neg-readme-only",
        {**F.CODE, "README.md": narrow},
        Case(
            "Update just the install step in the README — it should use `make install` now, not setup.py. Don't touch anything else.",
            {
                "install-fixed": regex(r"make install", f("README.md")),
                "only-install-changed": regex(
                    exact(
                        *narrow.split("python setup.py install")[:1],
                        r"[ \t]*make install[ \t]*",
                        narrow.split("python setup.py install")[1],
                    ),
                    f("README.md"),
                ),
                "no-docs-all": not_fired("docs-all"),
                "setup-py-gone": regex(
                    r"setup\.py install", f("README.md"), "not_contains"
                ),
                "no-docs-created": regex(r"^docs/", "files", "not_contains", "m"),
                "custom-section-kept": regex(
                    r"Running on the ops cron host", f("README.md")
                ),
            },
            15,
            300,
        ),
    )


def all_(root):
    _refresh(root)
    _bad_order(root)
    _refactor(root)
    _casual(root)
    _neg_readme_only(root)
