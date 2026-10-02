"""docs-improve eval cases."""

import common
import fixtures as F
from common import LE, Case, exact, exists, f, fired, llm, not_fired, regex

SKILL = "docs-improve"
MEASURED = "The reply reports measured numbers from before and after the change (e.g. over-cap doc count or line totals, 'X → Y'), and explicitly names every doc still over its cap (or states none remain). Fail on unquantified claims like 'the docs are now more concise'."

SAVE_SIG = "def save(records, db_path):"
STORE_BEFORE, STORE_AFTER = F.CODE["tally/store.py"].split(SAVE_SIG)
STORE_BEFORE += SAVE_SIG
DOCSTRING = (
    r'\n    (?:"""|' + "'''" + r')\s*[^\s"' + "'" + r'][\s\S]*?(?:"""|' + "'''" + ")"
)

BASE = {**F.CODE, "README.md": F.good_readme()}
HUB = "# Docs\n\n- [Getting started](GETTING_STARTED.md)\n- [Configuration](CONFIGURATION.md)\n- [Troubleshooting](TROUBLESHOOTING.md)\n"


def _overcap(root):
    common.write_case(
        root,
        "11-improve-overcap",
        {
            **BASE,
            **F.SMALL,
            "docs/README.md": HUB,
            "docs/TROUBLESHOOTING.md": F.troubleshooting(),
        },
        Case(
            "The docs are too long. Tighten them up.",
            {
                "no-part-n": regex(r"part-?\d", "files", "not_contains", "i"),
                "outcome": llm(
                    """
From the trace, judge the final state of the troubleshooting content. Pass only if: (1) no troubleshooting page is over 200 lines (split by subject such as install/auth/ingest, or cut); (2) the planted filler ("It is important to note", "simply", "Needless to say", "Please note that", "basically", "Obviously", "In this document we will") is gone from the final troubleshooting content; (3) if split, docs/README.md (or a troubleshooting hub) links every resulting page; (4) no error-code heading (INSTALL-01…INGEST-24) was silently lost: each was kept, merged, or dropped with the reply saying why (e.g. nothing in the code raises it).""",
                    "trace",
                ),
                "measured": llm(MEASURED),
                "skill-fired": fired(SKILL),
            },
            40,
            900,
        ),
    )


def _orphans(root):
    common.write_case(
        root,
        "12-improve-orphans",
        {**BASE, **F.SMALL},
        Case(
            "Improve the docs in this repo.",
            {
                "hub-created": exists("docs/README.md"),
                "hub-links-all": regex(
                    r"^(?=[\s\S]*\]\((?:\./)?GETTING_STARTED\.md\))(?=[\s\S]*\]\((?:\./)?CONFIGURATION\.md\))(?=[\s\S]*\]\((?:\./)?ingest-howto\.md\))(?=[\s\S]*\]\((?:\./)?ARCHITECTURE\.md\))",
                    f("docs/README.md"),
                ),
                "hub-under-cap": regex(
                    LE(120), f("docs/README.md"), "not_contains", weight=0.5
                ),
                "no-checklist-padding": llm(
                    "From the trace: the run did not create docs pages with placeholder/aspirational content (e.g. a troubleshooting page with invented errors, a roadmap, a FAQ with made-up questions). Creating docs/README.md as a hub is fine; any other new page must contain only facts traceable to the tally code.",
                    "trace",
                ),
                "skill-fired": fired(SKILL),
            },
            40,
            900,
        ),
    )


def _audit(root):
    broken_hub = (
        "# Docs\n\n- [Install](install.md)\n- [Config](config.md)\n- [FAQ](faq.md)\n"
    )
    audit = {
        **BASE,
        **F.SMALL,
        "docs/README.md": broken_hub,
        "docs/CONFIGURATION.md": F.config_ref(),
        "docs/GETTING_STARTED.md": "# Getting started\n\nThis guide will walk you through a seamless setup. Simply run:\n\n1. `make install`\n2. `tally ingest events.csv`\n3. `tally report`\n",
    }
    common.write_case(
        root,
        "13-improve-audit",
        audit,
        Case(
            "Audit our documentation.",
            {
                "finds-overcap": regex(r"CONFIGURATION\.md", flags=None),
                "finds-issues": llm("""
The reply identifies all of: (1) docs/CONFIGURATION.md is over its cap (reference, 400 lines) and is mostly deprecated `legacy_alias_*` rows; (2) docs/README.md has broken links (install.md, config.md, faq.md do not exist); (3) fluff in docs/GETTING_STARTED.md ("This guide will walk you through", "seamless", "Simply"); (4) docs/ingest-howto.md and docs/ARCHITECTURE.md are unreachable from the hub — named as orphans/unreachable, or the reply states it linked both from the hub. Pass only if all four are named with their file."""),
                "skill-fired": fired(SKILL),
            },
            40,
            900,
        ),
    )


def _links(root):
    links = {
        **BASE,
        **F.SMALL,
        "docs/README.md": "# Docs\n\n- [Install](install.md)\n- [Config](config.md)\n- [Ingest](ingest-howto.md)\n- [Architecture](ARCHITECTURE.md)\n",
        "docs/ARCHITECTURE.md": "# Architecture\n\n`cli` -> `ingest` -> `store` (SQLite). Source: [ingest](../src/ingest.py), [store](../src/store.py).\n",
    }
    common.write_case(
        root,
        "14-improve-links",
        links,
        Case(
            "Half the links in our docs 404. Sort it out.",
            {
                "hub-links-fixed": regex(
                    r"\]\((install|config)\.md\)", f("docs/README.md"), "not_contains"
                ),
                "arch-links-fixed": regex(
                    r"\]\(\.\./src/", f("docs/ARCHITECTURE.md"), "not_contains"
                ),
                "arch-links-retargeted": regex(
                    r"^(?=[\s\S]*\]\(\.\./tally/ingest\.py\))(?=[\s\S]*\]\(\.\./tally/store\.py\))",
                    f("docs/ARCHITECTURE.md"),
                    weight=0.5,
                ),
                "retargeted-not-deleted": llm(
                    "docs/README.md still links the getting-started and configuration content — i.e. it contains links to GETTING_STARTED.md and CONFIGURATION.md (the real files the broken install.md/config.md links meant) — rather than just deleting the broken entries.",
                    f("docs/README.md"),
                ),
                "skill-fired": fired(SKILL),
            },
            40,
            900,
        ),
    )


def _neg_docstring(root):
    common.write_case(
        root,
        "15-improve-neg-docstring",
        F.CODE,
        Case(
            "Add a docstring to `save()` in tally/store.py.",
            {
                "only-docstring-added": regex(
                    exact(STORE_BEFORE, DOCSTRING, STORE_AFTER), f("tally/store.py")
                ),
                "no-docs-skill": not_fired("docs-"),
                "no-docs-created": regex(r"^docs/", "files", "not_contains", "m"),
                "no-readme-created": exists("README.md", present=False),
            },
            15,
            300,
        ),
    )


def improve(root):
    _overcap(root)
    _orphans(root)
    _audit(root)
    _links(root)
    _neg_docstring(root)
