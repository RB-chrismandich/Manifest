"""docs-improve-readme eval cases."""

import common
import fixtures as F
from common import LE, Case, exact, exists, f, fired, llm, not_fired, regex

SKILL = "docs-improve-readme"

NO_FLUFF = regex(
    r"comprehensive|powerful|seamless|blazing fast|robust|state-of-the-art",
    f("README.md"),
    "not_contains",
    "i",
)
THR5 = regex(r"threshold[^\n]*\b5\b", f("README.md"), flags="i")
NO_THR10 = regex(
    r"default[^\n]*threshold[^\n]*\b10\b|threshold[^\n]*default[^\n]*\b10\b|default[^\n]*\b10\b[^\n]*threshold|\|\s*`?threshold`?\s*\|\s*`?10`?\s*\|",
    f("README.md"),
    "not_contains",
    "i",
)


def _bloated(root):
    common.write_case(
        root,
        "01-readme-bloated",
        {**F.CODE, "README.md": F.bloated_readme()},
        Case(
            "Our README is way too long and nobody reads it. Fix it.",
            {
                "under-cap": regex(LE(200), f("README.md"), "not_contains"),
                "fluff-gone": NO_FLUFF,
                "overflow-accounted": llm(
                    """
Judge from the trace and final reply. The original README carried five sections: a 12-entry hand-written TOC, a 40-line directory tree, a 30-question FAQ, a 30-entry changelog, and "Running on the ops cron host". Pass only if EACH is either (a) kept in the final README, (b) moved into a docs/ file that exists at the end of the run and is linked from the final README, or (c) deliberately dropped with the final reply saying so and why (e.g. the tree lists files that do not exist, the FAQ is filler). The ops cron host content must be (a) or (b), never dropped. Silent deletion of any section fails.""",
                    "trace",
                ),
                "content-quality": llm(
                    """
The final README (1) keeps a copy-pasteable quick start using only `make install` or `pip install -e .` followed by `tally ingest` / `tally report`; (2) states the threshold default as 5; (3) still contains the "Running on the ops cron host" content OR a one-line link to where it moved; (4) has no FAQ block, full directory tree, or changelog inlined; (5) invents no commands, options, or services absent from the original README and code. Pass only if all five hold.""",
                    f("README.md"),
                ),
                "measured-report": llm(
                    "The reply reports the README line count before and after as numbers (e.g. 'Lines: 250 → 90'), and names where any removed section went. Fail if it only asserts the README is 'shorter' or 'cleaner' without numbers.",
                    weight=0.5,
                ),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _missing(root):
    common.write_case(
        root,
        "02-readme-missing",
        F.CODE,
        Case(
            "There's no README in this repo yet. Write one.",
            {
                "readme-created": exists("README.md"),
                "real-install": regex(
                    r"make install|pip install -e \.", f("README.md")
                ),
                "no-invented-install": regex(
                    r"pip install tallyho|docker|brew install",
                    f("README.md"),
                    "not_contains",
                    "i",
                ),
                "facts-from-code": llm(
                    """
The README (1) describes tally as counting CSV events and flagging threshold breaches; (2) shows `tally ingest <file>` and `tally report` (with the optional `--threshold`); (3) gives the threshold default as 5 and mentions `tally.toml`; (4) states Python 3.11+ (tomllib); (5) makes no claim that cannot be traced to pyproject.toml, Makefile, or tally/*.py (a claim explicitly marked TODO is allowed; describing window_minutes as unused / not yet used is accurate, but attributing a future purpose to it is not). Pass only if all five hold.""",
                    f("README.md"),
                ),
                "under-cap": regex(LE(200), f("README.md"), "not_contains", weight=0.5),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _stale(root):
    common.write_case(
        root,
        "03-readme-stale",
        {**F.CODE, "README.md": F.stale_readme()},
        Case(
            "I think the README has drifted from the code. Can you bring it up to date?",
            {
                "no-make-docker": regex(r"make docker", f("README.md"), "not_contains"),
                "threshold-5": THR5,
                "no-threshold-10": NO_THR10,
                "python-311": regex(r"3\.11", f("README.md")),
                "usage-link-resolved": llm(
                    "Judge the final repository state from the trace. Pass if the final README.md does NOT link to docs/USAGE.md, OR the run created docs/USAGE.md with real content. Fail if README.md still links docs/USAGE.md and that file was never created.",
                    "trace",
                ),
                "support-kept": regex(r"Support", f("README.md"), weight=0.5),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _onboarding(root):
    common.write_case(
        root,
        "04-readme-onboarding",
        {**F.CODE, "README.md": F.stale_readme(onboarding=True)},
        Case(
            "New hires keep failing to get this running from the README alone. Clean it up so they can.",
            {
                "install-step": regex(
                    r"make install|pip install -e \.", f("README.md")
                ),
                "no-threshold-10": NO_THR10,
                "python-311": regex(r"3\.11", f("README.md")),
                "quickstart-runnable": llm(
                    """
A new hire reading top to bottom meets, in this order, an install step (`make install` or `pip install -e .`), then `tally ingest <csv>`, then `tally report` — in one code block or in consecutive sections (e.g. an Install section followed by a Quick start); creating a sample CSV first is fine. It names the CSV columns `event,ts` somewhere, and invents no step absent from the code (no docker, no PyPI install, no env vars besides optional proxy). Pass only if all hold.""",
                    f("README.md"),
                ),
                "skill-fired": fired(SKILL),
            },
            30,
            600,
        ),
    )


def _neg_typo(root):
    good = F.good_readme(typo=True)
    common.write_case(
        root,
        "05-readme-neg-typo",
        {**F.CODE, "README.md": good},
        Case(
            "Fix the typo 'recieve' in README.md.",
            {
                "typo-fixed": regex(r"recieve", f("README.md"), "not_contains"),
                "only-typo-changed": regex(
                    exact(
                        *good.split("recieve")[:1],
                        "receive",
                        good.split("recieve")[1],
                    ),
                    f("README.md"),
                ),
                "no-docs-skill": not_fired("docs-"),
                "not-truncated": regex(LE(len(good.splitlines()) - 3), f("README.md")),
                "not-expanded": regex(
                    LE(len(good.splitlines()) + 3), f("README.md"), "not_contains"
                ),
                "custom-section-kept": regex(
                    r"Running on the ops cron host", f("README.md")
                ),
                "no-docs-created": regex(r"^docs/", "files", "not_contains", "m"),
            },
            15,
            300,
        ),
    )


def readme(root):
    _bloated(root)
    _missing(root)
    _stale(root)
    _onboarding(root)
    _neg_typo(root)
