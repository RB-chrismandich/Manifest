"""C-DUPE (CON-003) — repeated blocks within a file and across the changed set.

Comparison is on normalized lines, so reformatting or a differing trailing
comment does not hide a copy. Structural filler is dropped first: a run of
twelve `pass` lines repeating is not duplication, and a check that says it is
gets ignored within a day.
"""

from __future__ import annotations

import hashlib
import re

from ..findings import Finding
from ..registry import Registry
from ..source import SourceFile

CHECK = "C-DUPE"
ARTICLE = "CON-003"

# Lines that carry no design decision. Repetition of these is the language's
# grammar, not the author's copy-paste.
FILLER = {
    "pass",
    "...",
    "return",
    "continue",
    "break",
    "raise",
    "{",
    "}",
    "(",
    ")",
    "[",
    "]",
    "});",
    "};",
    "end",
    "fi",
    "done",
    "esac",
    ";;",
    "else",
    "else:",
    "try:",
    "do",
    "then",
    "*/",
    "/*",
}

_STRING_RE = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")
_WS_RE = re.compile(r"\s+")


def run(src: SourceFile, registry: Registry) -> list[Finding]:
    """Report blocks repeated within this file after normalization (CON-003)."""
    if src.language is None:
        return []
    window = src.language.threshold("duplicate_block_lines")
    if not window:
        return []

    kept = _normalize(src)
    if len(kept) < window * 2:
        return []

    seen: dict[str, int] = {}
    findings: list[Finding] = []
    reported: set[str] = set()
    index = 0
    while index + window <= len(kept):
        block = kept[index : index + window]
        digest = hashlib.sha1("\n".join(text for _, text in block).encode()).hexdigest()
        first = seen.get(digest)
        if first is None:
            seen[digest] = block[0][0]
            index += 1
            continue
        if digest not in reported:
            reported.add(digest)
            findings.append(
                Finding(
                    check=CHECK,
                    article=ARTICLE,
                    severity="warn",
                    path=src.path,
                    line=block[0][0],
                    message=f"{window} lines repeat a block first seen at line {first}",
                    remedy="extract it to one shared definition and delete both copies",
                )
            )
        index += window  # skip past the duplicate rather than re-reporting each shift
    return findings


def _normalize(src: SourceFile) -> list[tuple[int, str]]:
    """(line number, normalized text) for lines that carry a decision."""
    prefix = src.language.comment_prefix
    kept = []
    for number, raw in enumerate(src.lines, start=1):
        text = _strip_comment(raw, prefix).strip()
        if not text or text in FILLER:
            continue
        kept.append((number, _WS_RE.sub(" ", text)))
    return kept


def _strip_comment(line: str, prefix: str) -> str:
    """Drop a trailing comment without cutting inside a string literal."""
    masked = _STRING_RE.sub(lambda m: "\x00" * len(m.group(0)), line)
    position = masked.find(prefix)
    return line if position < 0 else line[:position]
