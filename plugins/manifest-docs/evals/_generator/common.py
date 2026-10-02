"""Shared grader/prompt-building helpers and the write_case entry point.

Every skill-specific case-builder module (readme.py, diagrams.py, improve.py,
all_.py) imports these directly, but calls ``common.write_case`` through the
module (not via a bound ``from common import write_case``) so verify.py can
monkeypatch it in one place to capture fixtures without touching disk.
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import fixtures as F

TOOLS = ["Skill", "Bash", "Read", "Write", "Edit", "Glob", "Grep"]


def LE(n: int) -> str:
    """Regex that matches when a file has more than n lines (splitlines semantics)."""
    return f"^(?:[^\\n]*\\n){{{n}}}[\\s\\S]"


def IN_MERMAID(word: str) -> str:
    """Regex that matches `word` inside a single ```mermaid fenced block."""
    return "```mermaid(?:(?!```)[\\s\\S])*" + word + "(?:(?!```)[\\s\\S])*```"


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
    return "".join(
        "\\n" if ch == "\n" else "\\" + ch if ch in special else ch for ch in text
    )


def exact(before, middle, after):
    """Whole-file match: literal before/after, regex middle (the one permitted edit)."""
    return "^" + esc(before) + middle + esc(after) + r"\n*$"


def not_fired(match):
    return {
        "type": "tool_used",
        "tool": "Skill",
        "input_match": match,
        "min": 0,
        "max": 0,
        "arm": "both",
    }, ""


def fired(skill):
    return {"type": "tool_used", "tool": "Skill", "input_match": skill + "(?!-)"}, ""


@dataclass
class Case:
    """The behavioral half of a case — everything write_case needs besides
    where it goes (root/slug) and what fixture it starts from (files)."""

    ask: str
    graders: dict
    turns: int
    timeout: int
    tools: list = field(default_factory=lambda: TOOLS)


def write_case(root, slug, files, case):
    case_dir = os.path.join(root, slug)
    shutil.rmtree(
        os.path.join(case_dir, "graders"), ignore_errors=True
    )  # drop removed/renamed graders
    os.makedirs(os.path.join(case_dir, "graders"))
    head = fm(
        {
            "max_turns": case.turns,
            "timeout_seconds": case.timeout,
            "allowed_tools": case.tools,
            "model": "sonnet",
            "runs": 3,
        }
    )
    body = (F.setup_block(files) if files else "") + case.ask.strip() + "\n"
    Path(case_dir, "prompt.md").write_text(head + body)
    for name, (meta, text) in case.graders.items():
        Path(case_dir, "graders", name + ".md").write_text(
            fm(meta) + (text + "\n" if text else "")
        )
