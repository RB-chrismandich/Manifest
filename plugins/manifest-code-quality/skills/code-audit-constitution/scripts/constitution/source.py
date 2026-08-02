"""One parsed file, plus the exemptions its author declared.

Every check reads this; none of them re-open the file or re-parse the AST.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .registry import Language, Registry

# `# constitution: exempt C-DATA — reason`. The reason group is optional so the
# checker can tell "exempted with a reason" from "exempted silently" and treat
# the second as a finding rather than a suppression.
EXEMPT_RE = re.compile(
    r"constitution:\s*exempt\s+(?P<check>C-[A-Z]+)\s*"
    # \u2014 em dash, \u2013 en dash: both are typed by hand in real comments.
    r"(?:[\u2014\u2013]|--|-)?\s*(?P<reason>\S.*)?$"
)

# How many lines below the marker it covers. Three is enough to sit above a
# decorator or an `except` line without silently blanketing a whole function.
EXEMPT_SPAN = 3


@dataclass(frozen=True, slots=True)
class Exemption:
    check: str
    line: int
    reason: str | None

    def covers(self, line: int) -> bool:
        return self.line <= line <= self.line + EXEMPT_SPAN


@dataclass(slots=True)
class SourceFile:
    path: Path
    text: str
    lines: list[str]
    language: Language | None
    tree: ast.Module | None = None
    exemptions: list[Exemption] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path, registry: Registry) -> SourceFile:
        text = path.read_text(encoding="utf-8", errors="replace")
        return cls.from_text(path, text, registry)

    @classmethod
    def from_text(cls, path: Path, text: str, registry: Registry) -> SourceFile:
        language = registry.language_for(path)
        lines = text.splitlines()
        tree = None
        if language is not None and language.key == "python":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                # An unparseable file is the editor's problem, not the
                # constitution's; the line-based checks still apply.
                tree = None
        return cls(
            path=path,
            text=text,
            lines=lines,
            language=language,
            tree=tree,
            exemptions=_parse_exemptions(lines),
        )

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def exemption_for(self, check: str, line: int) -> Exemption | None:
        for exemption in self.exemptions:
            if exemption.check == check and exemption.covers(line):
                return exemption
        return None

    def span_text(self, start: int, end: int) -> str:
        """1-indexed, inclusive on both ends."""
        return "\n".join(self.lines[max(start - 1, 0) : end])


def _parse_exemptions(lines: list[str]) -> list[Exemption]:
    found = []
    for number, line in enumerate(lines, start=1):
        match = EXEMPT_RE.search(line)
        if match:
            reason = (match.group("reason") or "").strip() or None
            found.append(
                Exemption(check=match.group("check"), line=number, reason=reason)
            )
    return found
