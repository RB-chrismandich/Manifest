"""C-ERR (CON-007) — over-broad catches, swallowed failures, discarded causes.

Python only: the shell equivalents are already covered by `shell-audit-errexit`
and `shell-audit-pipefail`, and re-implementing them here would be the exact
duplication CON-003 forbids.
"""

from __future__ import annotations

import ast

from ..findings import Finding
from ..registry import Registry
from ..source import SourceFile

CHECK = "C-ERR"
ARTICLE = "CON-007"

BLANKET = {"Exception", "BaseException"}
LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "print",
}


def run(src: SourceFile, registry: Registry) -> list[Finding]:
    """Report over-broad catches, swallowed errors, and lost causes (CON-007)."""
    if src.tree is None:
        return []
    findings = []
    for node in ast.walk(src.tree):
        if isinstance(node, ast.ExceptHandler):
            findings.extend(_handler(src, node))
    return findings


def _handler(src: SourceFile, node: ast.ExceptHandler):
    if node.type is None:
        yield _finding(
            src,
            node.lineno,
            "error",
            "bare `except:` catches control-flow exceptions too",
            "catch the specific type this block can actually recover from",
        )
    elif _names(node.type) & BLANKET:
        yield _finding(
            src,
            node.lineno,
            "warn",
            "blanket `except Exception` hides failures the caller needed",
            "narrow it, or state the reason with `constitution: exempt C-ERR — <why>`",
        )

    raises = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
    if raises:
        yield from _reraise(src, node, raises)
        return

    body = [stmt for stmt in node.body if not _is_docstring(stmt)]
    if _only_filler(body) or _only_logging(body):
        yield _finding(
            src,
            node.lineno,
            "error",
            "exception is swallowed: caught, then neither re-raised nor acted on",
            "re-raise with context, return a documented fallback, or say what was lost",
        )


def _reraise(src: SourceFile, node: ast.ExceptHandler, raises: list[ast.Raise]):
    if not node.name:
        return  # nothing was bound, so there is no cause to attach
    for raise_node in raises:
        if raise_node.exc is None:
            return  # bare `raise` re-raises the original, cause intact
        if raise_node.cause is None:
            yield _finding(
                src,
                raise_node.lineno,
                "warn",
                "re-raise discards the original cause",
                f"`raise ... from {node.name}` so the traceback survives",
            )


def _names(node) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Tuple):
        return {name for element in node.elts for name in _names(element)}
    return set()


def _is_docstring(stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _only_filler(body: list) -> bool:
    return bool(body) and all(isinstance(stmt, ast.Pass) for stmt in body)


def _only_logging(body: list) -> bool:
    if not body:
        return False
    for stmt in body:
        if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
            return False
        func = stmt.value.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in LOG_METHODS:
            return False
    return True


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
