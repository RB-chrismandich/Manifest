"""C-SIZE (CON-002) — file, class, function, parameter, and nesting ceilings.

Every language gets the file ceiling from its line count. Python additionally
gets the structural ceilings from its AST; other languages get the file ceiling
only, which is honest rather than pretending to a precision we do not have.
"""

from __future__ import annotations

import ast

from ..findings import Finding
from ..registry import Registry
from ..source import SourceFile

CHECK = "C-SIZE"
ARTICLE = "CON-002"

# Fraction of a ceiling at which the file is reported as approaching it. This is
# what lets the pre-write hook say "480 of 500" before the edit rather than
# after, which is the whole point of a ceiling.
NEAR_RATIO = 0.9

# Bound parameters the author did not choose.
IMPLICIT_PARAMS = {"self", "cls"}


def run(src: SourceFile, registry: Registry) -> list[Finding]:
    """Report every ceiling this file crosses (CON-002)."""
    language = src.language
    if language is None:
        return []

    findings = list(_file_size(src))
    if src.tree is not None:
        findings.extend(_python_structure(src))
    return findings


def _file_size(src: SourceFile):
    ceiling = src.language.threshold("file_lines")
    if not ceiling:
        return
    count = src.line_count
    if count > ceiling:
        yield _finding(
            src,
            1,
            "error",
            f"file is {count} lines (ceiling {ceiling})",
            "split it along a responsibility seam, not at the midpoint",
        )
    elif count >= int(ceiling * NEAR_RATIO):
        yield _finding(
            src,
            1,
            "warn",
            f"file is {count} of {ceiling} lines",
            "the next responsibility added here belongs in a new module",
        )


def _python_structure(src: SourceFile):
    language = src.language
    class_ceiling = language.threshold("class_lines")
    method_ceiling = language.threshold("methods_per_class")
    function_ceiling = language.threshold("function_lines")
    param_ceiling = language.threshold("parameters")
    nesting_ceiling = language.threshold("nesting_depth")

    for node in ast.walk(src.tree):
        if isinstance(node, ast.ClassDef):
            yield from _class_size(src, node, class_ceiling, method_ceiling)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _function_size(
                src, node, function_ceiling, param_ceiling, nesting_ceiling
            )


def _class_size(
    src: SourceFile, node: ast.ClassDef, class_ceiling: int, method_ceiling: int
):
    span = _span(node)
    if class_ceiling and span > class_ceiling:
        yield _finding(
            src,
            node.lineno,
            "error",
            f"class `{node.name}` is {span} lines (ceiling {class_ceiling})",
            "split the state it owns from the behavior it merely hosts",
        )
    methods = [
        c for c in node.body if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if method_ceiling and len(methods) > method_ceiling:
        yield _finding(
            src,
            node.lineno,
            "error",
            f"class `{node.name}` has {len(methods)} methods (ceiling {method_ceiling})",
            "find the subset touching a disjoint set of attributes and extract it",
        )


def _function_size(
    src: SourceFile,
    node,
    function_ceiling: int,
    param_ceiling: int,
    nesting_ceiling: int,
):
    span = _span(node)
    if function_ceiling and span > function_ceiling:
        yield _finding(
            src,
            node.lineno,
            "error",
            f"function `{node.name}` is {span} lines (ceiling {function_ceiling})",
            "a setup/do/format shape is three functions, not one",
        )

    args = node.args
    named = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    count = len([a for a in named if a.arg not in IMPLICIT_PARAMS])
    if param_ceiling and count > param_ceiling:
        yield _finding(
            src,
            node.lineno,
            "warn",
            f"function `{node.name}` takes {count} parameters (ceiling {param_ceiling})",
            "the arguments that always travel together are a record; declare it",
        )

    depth = _max_depth(node)
    if nesting_ceiling and depth > nesting_ceiling:
        yield _finding(
            src,
            node.lineno,
            "warn",
            f"function `{node.name}` nests {depth} deep (ceiling {nesting_ceiling})",
            "guard-clause the preconditions and return early",
        )


def _span(node) -> int:
    end = getattr(node, "end_lineno", None) or node.lineno
    return end - node.lineno + 1


def _max_depth(node, depth: int = 0) -> int:
    """Deepest nesting of control-flow bodies inside a function."""
    nesting_types = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.Try,
    )
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # a nested definition has its own budget
        step = 1 if isinstance(child, nesting_types) else 0
        best = max(best, _max_depth(child, depth + step))
    return best


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
