"""C-DATA (CON-004) — structured payloads embedded as source literals.

The hard part is not finding long literals, it is not crying wolf. Every guard
below corresponds to a real false positive observed while surveying this repo's
138 Python files, and each is pinned by a named test.
"""

from __future__ import annotations

import ast
import json
import re

from ..findings import Finding
from ..registry import Registry
from ..source import SourceFile

CHECK = "C-DATA"
ARTICLE = "CON-004"

# `{name}` / `{name.attr}` / `{0}` — a placeholder, not a JSON brace.
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_0-9][\w.\[\]]*\}")
KEY_VALUE_RE = re.compile(r'^\s*[-"\']?[\w.\- ]+["\']?\s*:\s+\S')
LIST_ITEM_RE = re.compile(r"^\s*-\s+\S")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")
TAG_RE = re.compile(r"<[a-zA-Z][\w-]*[\s/>]")
SQL_RE = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+TABLE)\b", re.I
)

# Heredoc delimiters that never denote a data payload: this repo mandates
# `--help` text as a heredoc, and a `<< PY` block is embedded code, which is a
# different problem with a different fix.
EXEMPT_DELIMITERS = {
    "USAGE",
    "HELP",
    "EOF_USAGE",
    "PY",
    "PYTHON",
    "PYTHON3",
    "RUBY",
    "PERL",
    "NODE",
    "JS",
    "AWK",
    "SH",
    "BASH",
}

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(?P<delim>[A-Za-z_][A-Za-z_0-9]*)\1")

# Fraction of a collection's elements that must be literal for it to be data
# rather than a structure assembled at runtime.
LITERAL_RATIO = 0.7


def run(src: SourceFile, registry: Registry) -> list[Finding]:
    """Report structured payloads embedded as literals in this file (CON-004)."""
    if src.language is None:
        return []
    check = registry.checks.get(CHECK)
    if check is None:
        return []
    if src.tree is not None:
        return list(_python(src, check))
    return list(_line_based(src, check))


# ---------------------------------------------------------------------------
# Python — AST, because every regex approach misreads a docstring that happens
# to document key: value fields.
# ---------------------------------------------------------------------------


def _python(src: SourceFile, check):
    tree = src.tree
    docstrings = _docstring_nodes(tree)
    sql_args = _sql_argument_nodes(tree)
    names = _assigned_names(tree)
    string_ceiling = src.language.threshold("payload_string_lines")
    container_ceiling = src.language.threshold("payload_container_lines")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Constant, ast.JoinedStr)) and _is_str_node(node):
            if id(node) in docstrings or id(node) in sql_args:
                continue
            finding = _string_finding(src, check, node, names, string_ceiling)
            if finding:
                yield finding

    if container_ceiling:
        yield from _containers(src, check, tree, names, container_ceiling)


def _string_finding(src: SourceFile, check, node, names, ceiling: int):
    span = _span(node)
    if not ceiling or span < ceiling:
        return None
    text = src.span_text(node.lineno, getattr(node, "end_lineno", node.lineno))
    if SQL_RE.search(text):
        return None

    label = names.get(id(node))
    where = f"`{label}` " if label else ""
    ratio = _interpolation_ratio(text, span)
    if ratio > check.template_interpolation_ratio:
        return _finding(
            src,
            node.lineno,
            check.severity_for(span),
            f"{where}is a {span}-line code/prompt template embedded as a literal",
            f"move it to {_data_dir(src, 'templates')}/<name>.tmpl and render it; keep the interpolation",
        )
    if not _resembles_data(text):
        return None
    return _finding(
        src,
        node.lineno,
        check.severity_for(span),
        f"{where}embeds a {span}-line structured payload as a literal",
        f"move it to {_data_dir(src, 'data')}/<subject>.<ext> and load it through one loader",
    )


def _containers(src: SourceFile, check, tree, names, ceiling: int):
    """Top-down so a nested literal is not reported twice under its parent."""
    stack = list(ast.iter_child_nodes(tree))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
            span = _span(node)
            if span >= ceiling and _literal_ratio(node) >= LITERAL_RATIO:
                label = names.get(id(node))
                where = f"`{label}` " if label else ""
                yield _finding(
                    src,
                    node.lineno,
                    check.severity_for(span),
                    f"{where}is a {span}-line literal data table in source",
                    f"move it to {_data_dir(src, 'config')}/<subject>.yml and load it through one loader",
                )
                continue  # do not descend into a span already reported
        stack.extend(ast.iter_child_nodes(node))


def _docstring_nodes(tree) -> set[int]:
    """Ids of the string nodes that are docstrings, by position not by content."""
    found = set()
    for owner in ast.walk(tree):
        if isinstance(
            owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(owner, "body", None)
            if body and isinstance(body[0], ast.Expr) and _is_str_node(body[0].value):
                found.add(id(body[0].value))
    return found


def _sql_argument_nodes(tree) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in {"execute", "executemany", "executescript"}:
            found.update(id(arg) for arg in node.args)
    return found


def _assigned_names(tree) -> dict[int, str]:
    names: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.value is not None:
            target = node.targets[0] if node.targets else None
            if isinstance(target, ast.Name):
                names[id(node.value)] = target.id
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value
        ):
            names[id(node.value)] = node.target.id
    return names


def _is_str_node(node) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _literal_ratio(node) -> float:
    """Fraction of a collection's elements that are literal, not computed."""
    elements = list(node.values) if isinstance(node, ast.Dict) else list(node.elts)
    if not elements:
        return 0.0
    literal = sum(1 for e in elements if _is_literal(e))
    return literal / len(elements)


def _is_literal(node) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_literal(v) for v in node.values)
    return False


# ---------------------------------------------------------------------------
# Every other language — delimited blocks, since we have no parser for them.
# ---------------------------------------------------------------------------


def _line_based(src: SourceFile, check):
    ceiling = src.language.threshold("payload_string_lines")
    if not ceiling:
        return
    for start, end, body, delimiter in _blocks(src):
        span = end - start + 1
        if span < ceiling or delimiter.upper() in EXEMPT_DELIMITERS:
            continue
        if SQL_RE.search(body) or not _resembles_data(body):
            continue
        yield _finding(
            src,
            start,
            check.severity_for(span),
            f"`{delimiter}` block embeds a {span}-line structured payload",
            f"move it to {_data_dir(src, 'templates')}/<name> and render or read it from there",
        )


def _blocks(src: SourceFile):
    """Yield (start, end, body, delimiter) for heredocs and raw-string blocks."""
    pending: tuple[int, str] | None = None
    body: list[str] = []
    for number, line in enumerate(src.lines, start=1):
        if pending is None:
            match = HEREDOC_RE.search(line)
            if match:
                pending = (number, match.group("delim"))
                body = []
            continue
        if line.strip() == pending[1]:
            yield pending[0], number, "\n".join(body), pending[1]
            pending = None
        else:
            body.append(line)


def _resembles_data(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    if _parses_as_json(text):
        return True
    key_values = sum(1 for line in lines if KEY_VALUE_RE.match(line))
    items = sum(1 for line in lines if LIST_ITEM_RE.match(line))
    headings = sum(1 for line in lines if HEADING_RE.match(line))
    tags = sum(1 for line in lines if TAG_RE.search(line))
    return key_values >= 3 or items >= 3 or headings >= 2 or tags >= 3


def _parses_as_json(text: str) -> bool:
    """Whether the span is literally JSON. Failure is an answer, not an error."""
    try:
        json.loads(text.strip().strip("\"'"))
    except (ValueError, TypeError):
        return False
    return True


def _interpolation_ratio(text: str, span: int) -> float:
    if span <= 0:
        return 0.0
    return len(PLACEHOLDER_RE.findall(text)) / span


def _data_dir(src: SourceFile, preferred: str) -> str:
    dirs = src.language.data_dirs
    for candidate in dirs:
        if candidate.endswith(preferred) or preferred in candidate:
            return candidate
    return dirs[0] if dirs else preferred


def _span(node) -> int:
    end = getattr(node, "end_lineno", None) or node.lineno
    return end - node.lineno + 1


def _finding(
    src: SourceFile, line: int, severity: str, message: str, remedy: str
) -> Finding:
    return Finding(
        check=CHECK,
        article=ARTICLE,
        severity=severity,
        path=src.path,
        line=line,
        message=message,
        remedy=remedy,
    )
