"""Write evals/<case>/ dirs for manifest-docs. Usage: gen.py <evals_dir> <skill>..."""
import os, shutil, sys

import fixtures as F

TOOLS = ["Skill", "Bash", "Read", "Write", "Edit", "Glob", "Grep"]
LE = lambda n: f"^(?:[^\\n]*\\n){{{n}}}[\\s\\S]"  # matches when a file has more than n lines (splitlines semantics)
IN_MERMAID = lambda word: "```mermaid(?:(?!```)[\\s\\S])*" + word + "(?:(?!```)[\\s\\S])*```"


def fm(d):
    out = []
    for k, v in d.items():
        if isinstance(v, list):
            v = "[" + ", ".join(v) + "]"
        elif isinstance(v, bool):
            v = str(v).lower()
        out.append(f"{k}: {v}")
    return "---\n" + "\n".join(out) + "\n---\n"


def f(path):
    return "{source: file, path: " + path + "}"


def regex(pattern, target="last_message", match="contains", flags=None, weight=None):
    d = {"type": "regex", "target": target, "match": match}
    if flags:
        d["flags"] = flags
    if weight:
        d["weight"] = weight
    return d, pattern


def llm(rubric, focus="last_message", weight=None):
    d = {"type": "llm", "focus": focus}
    if weight:
        d["weight"] = weight
    return d, rubric.strip()


def exists(path, present=True, weight=None):
    d = {"type": "file_exists", "path": path, "exists": present}
    if weight:
        d["weight"] = weight
    return d, ""


def esc(text):
    """Escape literal text for a regex portable across JS and Python engines."""
    special = ".*+?^${}()|[]\\/"
    return "".join("\\n" if ch == "\n" else "\\" + ch if ch in special else ch for ch in text)


def exact(before, middle, after):
    """Whole-file match: literal before/after, regex middle (the one permitted edit)."""
    return "^" + esc(before) + middle + esc(after) + r"\n*$"


def not_fired(match):
    return {"type": "tool_used", "tool": "Skill", "input_match": match, "min": 0, "max": 0, "arm": "both"}, ""


def fired(skill):
    return {"type": "tool_used", "tool": "Skill", "input_match": skill + "(?!-)"}, ""


def write_case(root, slug, files, ask, graders, turns, timeout, tools=TOOLS):
    case = os.path.join(root, slug)
    shutil.rmtree(os.path.join(case, "graders"), ignore_errors=True)  # drop removed/renamed graders
    os.makedirs(os.path.join(case, "graders"))
    head = fm({"max_turns": turns, "timeout_seconds": timeout, "allowed_tools": tools, "model": "sonnet", "runs": 3})
    body = (F.setup_block(files) if files else "") + ask.strip() + "\n"
    open(os.path.join(case, "prompt.md"), "w").write(head + body)
    for name, (meta, text) in graders.items():
        open(os.path.join(case, "graders", name + ".md"), "w").write(fm(meta) + (text + "\n" if text else ""))


def readme(root):
    s = "docs-improve-readme"
    no_fluff = regex(r"comprehensive|powerful|seamless|blazing fast|robust|state-of-the-art", f("README.md"), "not_contains", "i")
    thr5 = regex(r"threshold[^\n]*\b5\b", f("README.md"), flags="i")
    no_thr10 = regex(r"default[^\n]*threshold[^\n]*\b10\b|threshold[^\n]*default[^\n]*\b10\b|default[^\n]*\b10\b[^\n]*threshold|\|\s*`?threshold`?\s*\|\s*`?10`?\s*\|", f("README.md"), "not_contains", "i")
    write_case(root, "01-readme-bloated", {**F.CODE, "README.md": F.bloated_readme()},
        "Our README is way too long and nobody reads it. Fix it.", {
            "under-cap": regex(LE(200), f("README.md"), "not_contains"),
            "fluff-gone": no_fluff,
            "overflow-accounted": llm("""
Judge from the trace and final reply. The original README carried five sections: a 12-entry hand-written TOC, a 40-line directory tree, a 30-question FAQ, a 30-entry changelog, and "Running on the ops cron host". Pass only if EACH is either (a) kept in the final README, (b) moved into a docs/ file that exists at the end of the run and is linked from the final README, or (c) deliberately dropped with the final reply saying so and why (e.g. the tree lists files that do not exist, the FAQ is filler). The ops cron host content must be (a) or (b), never dropped. Silent deletion of any section fails.""", "trace"),
            "content-quality": llm("""
The final README (1) keeps a copy-pasteable quick start using only `make install` or `pip install -e .` followed by `tally ingest` / `tally report`; (2) states the threshold default as 5; (3) still contains the "Running on the ops cron host" content OR a one-line link to where it moved; (4) has no FAQ block, full directory tree, or changelog inlined; (5) invents no commands, options, or services absent from the original README and code. Pass only if all five hold.""", f("README.md")),
            "measured-report": llm("The reply reports the README line count before and after as numbers (e.g. 'Lines: 250 → 90'), and names where any removed section went. Fail if it only asserts the README is 'shorter' or 'cleaner' without numbers.", weight=0.5),
            "skill-fired": fired(s),
        }, 30, 600)
    write_case(root, "02-readme-missing", F.CODE,
        "There's no README in this repo yet. Write one.", {
            "readme-created": exists("README.md"),
            "real-install": regex(r"make install|pip install -e \.", f("README.md")),
            "no-invented-install": regex(r"pip install tallyho|docker|brew install", f("README.md"), "not_contains", "i"),
            "facts-from-code": llm("""
The README (1) describes tally as counting CSV events and flagging threshold breaches; (2) shows `tally ingest <file>` and `tally report` (with the optional `--threshold`); (3) gives the threshold default as 5 and mentions `tally.toml`; (4) states Python 3.11+ (tomllib); (5) makes no claim that cannot be traced to pyproject.toml, Makefile, or tally/*.py (a claim explicitly marked TODO is allowed; describing window_minutes as unused / not yet used is accurate, but attributing a future purpose to it is not). Pass only if all five hold.""", f("README.md")),
            "under-cap": regex(LE(200), f("README.md"), "not_contains", weight=0.5),
            "skill-fired": fired(s),
        }, 30, 600)
    write_case(root, "03-readme-stale", {**F.CODE, "README.md": F.stale_readme()},
        "I think the README has drifted from the code. Can you bring it up to date?", {
            "no-make-docker": regex(r"make docker", f("README.md"), "not_contains"),
            "threshold-5": thr5,
            "no-threshold-10": no_thr10,
            "python-311": regex(r"3\.11", f("README.md")),
            "usage-link-resolved": llm("Judge the final repository state from the trace. Pass if the final README.md does NOT link to docs/USAGE.md, OR the run created docs/USAGE.md with real content. Fail if README.md still links docs/USAGE.md and that file was never created.", "trace"),
            "support-kept": regex(r"Support", f("README.md"), weight=0.5),
            "skill-fired": fired(s),
        }, 30, 600)
    write_case(root, "04-readme-onboarding", {**F.CODE, "README.md": F.stale_readme(onboarding=True)},
        "New hires keep failing to get this running from the README alone. Clean it up so they can.", {
            "install-step": regex(r"make install|pip install -e \.", f("README.md")),
            "no-threshold-10": no_thr10,
            "python-311": regex(r"3\.11", f("README.md")),
            "quickstart-runnable": llm("""
A new hire reading top to bottom meets, in this order, an install step (`make install` or `pip install -e .`), then `tally ingest <csv>`, then `tally report` — in one code block or in consecutive sections (e.g. an Install section followed by a Quick start); creating a sample CSV first is fine. It names the CSV columns `event,ts` somewhere, and invents no step absent from the code (no docker, no PyPI install, no env vars besides optional proxy). Pass only if all hold.""", f("README.md")),
            "skill-fired": fired(s),
        }, 30, 600)
    good = F.good_readme(typo=True)
    write_case(root, "05-readme-neg-typo", {**F.CODE, "README.md": good},
        "Fix the typo 'recieve' in README.md.", {
            "typo-fixed": regex(r"recieve", f("README.md"), "not_contains"),
            "only-typo-changed": regex(exact(*good.split("recieve")[:1], "receive", good.split("recieve")[1]), f("README.md")),
            "no-docs-skill": not_fired("docs-"),
            "not-truncated": regex(LE(len(good.splitlines()) - 3), f("README.md")),
            "not-expanded": regex(LE(len(good.splitlines()) + 3), f("README.md"), "not_contains"),
            "custom-section-kept": regex(r"Running on the ops cron host", f("README.md")),
            "no-docs-created": regex(r"^docs/", "files", "not_contains", "m"),
        }, 15, 300)


MERMAID5 = r"(?:```mermaid[\s\S]*?){5}"
DIAG_OK = """
Check every Mermaid diagram in the file. (1) Syntax: each declares a diagram type on its first line (flowchart, sequenceDiagram, classDiagram, stateDiagram) and has no unclosed brackets, unclosed subgraphs, or prose lines inside the block. (2) Every internal component shown is a real part of the repo: tally.cli (ingest and report commands), tally.config, tally.ingest, tally.store, tally.report, or their functions. External actors are fine: the user/shell, the CSV input file, tally.toml, the SQLite database file, click. Invented components fail it: Redis, a queue, an API/web server, a cache, a separate database service. (3) Each diagram has at most 20 nodes and a short caption. Pass only if all three hold."""


def diagrams(root):
    s = "docs-generate-diagrams"
    page = "docs/ARCHITECTURE_DIAGRAMS.md"
    write_case(root, "06-diag-fresh", {**F.CODE, "README.md": F.good_readme()},
        f"Add architecture diagrams for this project in {page}.", {
            "has-mermaid": regex(r"```mermaid", f(page)),
            "at-most-4": regex(MERMAID5, f(page), "not_contains"),
            "matches-code": llm(DIAG_OK, f(page)),
            "under-cap": regex(LE(300), f(page), "not_contains", weight=0.5),
            "skill-fired": fired(s),
        }, 30, 600)
    write_case(root, "07-diag-huge", {**F.CODE, page: F.huge_diagrams()},
        f"The diagram doc ({page}) is huge and nobody can find anything in it. Sort it out.", {
            "no-part-n": regex(r"part-?\d", "files", "not_contains", "i"),
            "outcome": llm("""
From the trace, judge the final docs state. Pass only if: (1) no resulting diagram page holds more than 4 mermaid blocks or 300 lines; (2) the seven near-identical diagrams were consolidated or dropped rather than copied verbatim into new pages; (3) any hub page is navigation only, one line per child; (4) the final reply says which diagrams were dropped/merged and why.""", "trace"),
            "skill-fired": fired(s),
        }, 30, 600)
    write_case(root, "08-diag-stale", {**F.CODE, page: F.stale_diagrams()},
        f"Our diagrams in {page} are out of date — we ripped Redis out a while back. Update them to match the code.", {
            "redis-gone": regex(r"redis", f(page), "not_contains", "i"),
            "has-mermaid": regex(r"```mermaid", f(page)),
            "sqlite-in-diagram": regex(IN_MERMAID("sqlite"), f(page), flags="i"),
            "matches-code": llm(DIAG_OK, f(page)),
            "skill-fired": fired(s),
        }, 30, 600)
    flow = "docs/ingest-flow.md"
    write_case(root, "09-diag-sequence", {**F.CODE, "README.md": F.good_readme()},
        f"Draw a diagram of how one record gets from `tally ingest` into the database, and put it in {flow}.", {
            "has-mermaid": regex(r"```mermaid", f(flow)),
            "call-order": llm("""
The diagram shows this order and nothing invented in between: cli `ingest` command → config.load (db_path) → ingest.run → ingest.read_csv (csv.DictReader) → ingest.normalize (lower-cases event) → store.save → SQLite `events` table INSERT. Omitting config.load or the one-line ingest.run pass-through is fine; wrong order, invented steps (validation service, queue, cache) or missing store.save fail. Syntax must be valid Mermaid.""", f(flow)),
            "one-concept": regex(r"(?:```mermaid[\s\S]*?){3}", f(flow), "not_contains", weight=0.5),
            "skill-fired": fired(s),
        }, 30, 600)
    write_case(root, "10-diag-neg-syntax", None,
        "Quick question: what's the Mermaid syntax for grouping nodes in a subgraph inside a flowchart?", {
            "answers": regex(r"subgraph[\s\S]*\bend\b", flags="i"),
            "no-docs-skill": not_fired("docs-"),
            "no-files": regex(r"\S", "files", "not_contains"),
            "correct": llm("The reply shows a flowchart containing `subgraph <id>[<title>]` (or `subgraph title`) ... `end`, with nodes inside and an edge, in valid Mermaid syntax, and does not claim to have created or edited any file."),
        }, 5, 120, ["Skill", "Read", "Write"])


MEASURED = "The reply reports measured numbers from before and after the change (e.g. over-cap doc count or line totals, 'X → Y'), and explicitly names every doc still over its cap (or states none remain). Fail on unquantified claims like 'the docs are now more concise'."


SAVE_SIG = "def save(records, db_path):"
STORE_BEFORE, STORE_AFTER = F.CODE["tally/store.py"].split(SAVE_SIG)
STORE_BEFORE += SAVE_SIG
DOCSTRING = r'\n    (?:"""|' + "'''" + r')\s*[^\s"' + "'" + r'][\s\S]*?(?:"""|' + "'''" + ')'


def improve(root):
    s = "docs-improve"
    base = {**F.CODE, "README.md": F.good_readme()}
    hub = "# Docs\n\n- [Getting started](GETTING_STARTED.md)\n- [Configuration](CONFIGURATION.md)\n- [Troubleshooting](TROUBLESHOOTING.md)\n"
    write_case(root, "11-improve-overcap", {**base, **F.SMALL, "docs/README.md": hub, "docs/TROUBLESHOOTING.md": F.troubleshooting()},
        "The docs are too long. Tighten them up.", {
            "no-part-n": regex(r"part-?\d", "files", "not_contains", "i"),
            "outcome": llm("""
From the trace, judge the final state of the troubleshooting content. Pass only if: (1) no troubleshooting page is over 200 lines (split by subject such as install/auth/ingest, or cut); (2) the planted filler ("It is important to note", "simply", "Needless to say", "Please note that", "basically", "Obviously", "In this document we will") is gone from the final troubleshooting content; (3) if split, docs/README.md (or a troubleshooting hub) links every resulting page; (4) no error-code heading (INSTALL-01…INGEST-24) was silently lost: each was kept, merged, or dropped with the reply saying why (e.g. nothing in the code raises it).""", "trace"),
            "measured": llm(MEASURED),
            "skill-fired": fired(s),
        }, 40, 900)
    write_case(root, "12-improve-orphans", {**base, **F.SMALL},
        "Improve the docs in this repo.", {
            "hub-created": exists("docs/README.md"),
            "hub-links-all": regex(r"^(?=[\s\S]*\]\((?:\./)?GETTING_STARTED\.md\))(?=[\s\S]*\]\((?:\./)?CONFIGURATION\.md\))(?=[\s\S]*\]\((?:\./)?ingest-howto\.md\))(?=[\s\S]*\]\((?:\./)?ARCHITECTURE\.md\))", f("docs/README.md")),
            "hub-under-cap": regex(LE(120), f("docs/README.md"), "not_contains", weight=0.5),
            "no-checklist-padding": llm("From the trace: the run did not create docs pages with placeholder/aspirational content (e.g. a troubleshooting page with invented errors, a roadmap, a FAQ with made-up questions). Creating docs/README.md as a hub is fine; any other new page must contain only facts traceable to the tally code.", "trace"),
            "skill-fired": fired(s),
        }, 40, 900)
    broken_hub = "# Docs\n\n- [Install](install.md)\n- [Config](config.md)\n- [FAQ](faq.md)\n"
    audit = {**base, **F.SMALL, "docs/README.md": broken_hub, "docs/CONFIGURATION.md": F.config_ref(),
             "docs/GETTING_STARTED.md": "# Getting started\n\nThis guide will walk you through a seamless setup. Simply run:\n\n1. `make install`\n2. `tally ingest events.csv`\n3. `tally report`\n"}
    write_case(root, "13-improve-audit", audit,
        "Audit our documentation.", {
            "finds-overcap": regex(r"CONFIGURATION\.md", flags=None),
            "finds-issues": llm("""
The reply identifies all of: (1) docs/CONFIGURATION.md is over its cap (reference, 400 lines) and is mostly deprecated `legacy_alias_*` rows; (2) docs/README.md has broken links (install.md, config.md, faq.md do not exist); (3) fluff in docs/GETTING_STARTED.md ("This guide will walk you through", "seamless", "Simply"); (4) docs/ingest-howto.md and docs/ARCHITECTURE.md are unreachable from the hub — named as orphans/unreachable, or the reply states it linked both from the hub. Pass only if all four are named with their file."""),
            "skill-fired": fired(s),
        }, 40, 900)
    links = {**base, **F.SMALL, "docs/README.md": "# Docs\n\n- [Install](install.md)\n- [Config](config.md)\n- [Ingest](ingest-howto.md)\n- [Architecture](ARCHITECTURE.md)\n",
             "docs/ARCHITECTURE.md": "# Architecture\n\n`cli` -> `ingest` -> `store` (SQLite). Source: [ingest](../src/ingest.py), [store](../src/store.py).\n"}
    write_case(root, "14-improve-links", links,
        "Half the links in our docs 404. Sort it out.", {
            "hub-links-fixed": regex(r"\]\((install|config)\.md\)", f("docs/README.md"), "not_contains"),
            "arch-links-fixed": regex(r"\]\(\.\./src/", f("docs/ARCHITECTURE.md"), "not_contains"),
            "arch-links-retargeted": regex(r"^(?=[\s\S]*\]\(\.\./tally/ingest\.py\))(?=[\s\S]*\]\(\.\./tally/store\.py\))", f("docs/ARCHITECTURE.md"), weight=0.5),
            "retargeted-not-deleted": llm("docs/README.md still links the getting-started and configuration content — i.e. it contains links to GETTING_STARTED.md and CONFIGURATION.md (the real files the broken install.md/config.md links meant) — rather than just deleting the broken entries.", f("docs/README.md")),
            "skill-fired": fired(s),
        }, 40, 900)
    write_case(root, "15-improve-neg-docstring", F.CODE,
        "Add a docstring to `save()` in tally/store.py.", {
            "only-docstring-added": regex(exact(STORE_BEFORE, DOCSTRING, STORE_AFTER), f("tally/store.py")),
            "no-docs-skill": not_fired("docs-"),
            "no-docs-created": regex(r"^docs/", "files", "not_contains", "m"),
            "no-readme-created": exists("README.md", present=False),
        }, 15, 300)


ALL_REPORT = """
The final reply is a measured refresh report that (1) states the order the README, diagram, and docs-audit work ran in, with a reason; (2) gives each of the three parts an outcome (success/failed/skipped with the error); (3) shows before → after numbers for over-cap docs or line totals; (4) names every doc still over cap, or states none remain. Fail if any of the four is missing."""


MERMAID_WRITE = (r'"file_path":"[^"]*/docs/[^"]*\.md","content":"(?:[^"\\]|\\.)*```mermaid'
                 r'|"file_path":"[^"]*/docs/[^"]*\.md",(?:"old_string":"(?:[^"\\]|\\.)*",)?"new_string":"(?:[^"\\]|\\.)*```mermaid'
                 r'|"command":"(?:[^"\\]|\\.)*docs/[^"\\\s]*\.md(?:[^"\\]|\\.)*```mermaid'
                 r'|"command":"(?:[^"\\]|\\.)*```mermaid(?:[^"\\]|\\.)*docs/[^"\\\s]*\.md')
CONFIG_FACTS = r"^(?=[\s\S]*threshold[^\n]*\b5\b)(?=[\s\S]*tally\.db)(?=[\s\S]*window_minutes[^\n]*\b60\b)"
DOCS_REACHABLE = (r"\]\((?:\./)?docs/(?:README|index)\.md\)"
                  r"|^(?=[\s\S]*\]\((?:\./)?docs/GETTING_STARTED\.md[)#])(?=[\s\S]*\]\((?:\./)?docs/CONFIGURATION\.md[)#])")
TS_FLUFF = r"it is important to note|simply|needless to say|please note that|basically|obviously|in this document we will"


def all_(root):
    s = "docs-all"
    tools = TOOLS + ["Agent"]
    messy = {**F.CODE, "README.md": F.bloated_readme(), **F.SMALL,
             "docs/TROUBLESHOOTING.md": F.troubleshooting(), "docs/CONFIGURATION.md": F.config_ref()}
    common = {
        "readme-under-cap": regex(LE(200), f("README.md"), "not_contains"),
        "diagrams-created": regex(MERMAID_WRITE, "trace"),
        "config-under-cap": regex(LE(400), f("docs/CONFIGURATION.md"), "not_contains"),
        "config-facts-kept": regex(CONFIG_FACTS, f("docs/CONFIGURATION.md"), flags="i"),
        "troubleshooting-fluff-gone": regex(TS_FLUFF, f("docs/TROUBLESHOOTING.md"), "not_contains", "i", weight=0.5),
        "docs-reachable": regex(DOCS_REACHABLE, f("README.md")),
        "report": llm(ALL_REPORT),
        "skill-fired": fired(s),
    }
    write_case(root, "16-all-refresh", messy, "Refresh all the docs in this repo.", common, 60, 1500, tools)
    write_case(root, "17-all-bad-order", messy,
        "Refresh all the docs. Run them in this order: --order docs-improve,docs-improve-readme,docs-generate-diagrams", {
            "warns-order": llm("The reply warns that the requested order puts the docs audit (docs-improve) first although it depends on the README and diagram updates — i.e. it flags the dependency violation — and states the order it actually used. Running the requested order unchanged, with that warning, is correct per the skill; silently running it with no warning fails, and silently reordering without saying so also fails."),
            "readme-under-cap": common["readme-under-cap"],
            "diagrams-created": common["diagrams-created"],
            **{k: common[k] for k in ("config-under-cap", "config-facts-kept", "troubleshooting-fluff-gone", "docs-reachable")},
            "report": llm(ALL_REPORT, weight=0.5),
            "skill-fired": fired(s),
        }, 60, 1500, tools)
    refactor = {k: v for k, v in F.CODE.items() if k != "tally/ingest.py"}
    refactor.update(F.SPLIT_INGEST)
    refactor.update({"README.md": F.good_readme(), "docs/ARCHITECTURE_DIAGRAMS.md": F.split_stale_diagrams(), **F.SMALL})
    write_case(root, "18-all-refactor", refactor,
        "We just split ingest into a package with separate reader and normalize modules. Update all the docs to match.", {
            "diagram-updated": regex(r"ingest\.py", f("docs/ARCHITECTURE_DIAGRAMS.md"), "not_contains"),
            "diagram-has-reader": regex(IN_MERMAID("reader"), f("docs/ARCHITECTURE_DIAGRAMS.md"), flags="i"),
            "diagram-has-normalize": regex(IN_MERMAID("normalize"), f("docs/ARCHITECTURE_DIAGRAMS.md"), flags="i"),
            "diagram-accurate": llm(DIAG_OK + " Also: the ingest path is shown as the tally.ingest package with reader (read_csv) and normalize as separate nodes, and no node for a single tally/ingest.py file. Either shape is accurate: a data-flow chain (reader → normalize → store) or a call graph where the package __init__ / ingest.run calls reader, normalize, and store. Fail only if the modules are wired in a way the code contradicts (e.g. store calling normalize, reader writing to the store).", f("docs/ARCHITECTURE_DIAGRAMS.md")),
            "report": llm(ALL_REPORT, weight=0.5),
            "skill-fired": fired(s),
        }, 60, 1500, tools)
    write_case(root, "19-all-casual", messy,
        "honestly the docs are a mess across the board — readme, diagrams, the docs folder. update everything at once", {
            **common}, 60, 1500, tools)
    narrow = F.good_readme(install="python setup.py install")
    write_case(root, "20-all-neg-readme-only", {**F.CODE, "README.md": narrow},
        "Update just the install step in the README — it should use `make install` now, not setup.py. Don't touch anything else.", {
            "install-fixed": regex(r"make install", f("README.md")),
            "only-install-changed": regex(exact(*narrow.split("python setup.py install")[:1], r"[ \t]*make install[ \t]*", narrow.split("python setup.py install")[1]), f("README.md")),
            "no-docs-all": not_fired("docs-all"),
            "setup-py-gone": regex(r"setup\.py install", f("README.md"), "not_contains"),
            "no-docs-created": regex(r"^docs/", "files", "not_contains", "m"),
            "custom-section-kept": regex(r"Running on the ops cron host", f("README.md")),
        }, 15, 300)


SKILLS = {"readme": readme, "diagrams": diagrams, "improve": improve, "all": all_}

if __name__ == "__main__":
    root = sys.argv[1]
    for name in sys.argv[2:]:
        SKILLS[name](root)
