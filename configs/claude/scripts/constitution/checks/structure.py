"""The advisory checks: C-TYPE, C-TEST, C-STRUCT, C-DOC.

All four are heuristics, and all four are marked `advisory: true` in the
registry. They report at every layer and block at none — a heuristic that blocks
teaches people to suppress it, which costs more than the finding was worth.
"""

from __future__ import annotations

import ast
import re

from ..findings import Finding
from ..registry import Registry
from ..source import SourceFile

UNTYPED_MAPPINGS = {"dict", "Dict", "Mapping", "MutableMapping"}
COMMENTED_CODE_RE = re.compile(
    r"^\s*#\s*(def |class |return |if |for |while |import |from |\w+\s*=\s*\S)"
)
MIN_COMMENTED_CODE_RUN = 3

# Each advisory check's article. Derivable from the registry, but these four are
# fixed by this module's own structure, and passing the pair to every call site
# pushed the helper over the parameter ceiling this package enforces.
ARTICLES = {
    "C-TYPE": "CON-005",
    "C-DOC": "CON-010",
    "C-TEST": "CON-008",
    "C-STRUCT": "CON-009",
}


def run(src: SourceFile, registry: Registry) -> list[Finding]:
    """Report the four advisory findings: typing, tests, structure, docs."""
    if src.language is None:
        return []
    findings: list[Finding] = []
    if src.tree is not None:
        findings.extend(_boundaries(src))
        findings.extend(_docs(src))
        findings.extend(_mirroring_test(src))
    findings.extend(_commented_out_code(src))
    findings.extend(_help_contract(src))
    return findings


def _boundaries(src: SourceFile):
    """C-TYPE — a public function taking or returning a bare mapping."""
    for node in _public_functions(src.tree):
        args = node.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            if arg.arg in {"self", "cls"}:
                continue
            if arg.annotation is None:
                yield _finding(
                    "C-TYPE",
                    src,
                    node.lineno,
                    f"`{node.name}` parameter `{arg.arg}` is unannotated",
                    "annotate it; an unannotated public parameter is unchecked by the type checker",
                )
            elif _is_bare_mapping(arg.annotation):
                yield _finding(
                    "C-TYPE",
                    src,
                    node.lineno,
                    f"`{node.name}` accepts an unparameterized mapping as `{arg.arg}`",
                    "declare the shape: a validated model for external input, a dataclass internally",
                )
        if node.returns is not None and _is_bare_mapping(node.returns):
            yield _finding(
                "C-TYPE",
                src,
                node.lineno,
                f"`{node.name}` returns an unparameterized mapping",
                "return a declared record so callers cannot mistype a key",
            )


def _docs(src: SourceFile):
    """C-DOC — undocumented public surface."""
    if src.tree.body and not ast.get_docstring(src.tree):
        yield _finding(
            "C-DOC",
            src,
            1,
            "module has no docstring",
            "one sentence on what this module is for",
        )
    for node in ast.walk(src.tree):
        is_class = isinstance(node, ast.ClassDef)
        is_function = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if not (is_class or is_function) or node.name.startswith("_"):
            continue
        if not ast.get_docstring(node):
            yield _finding(
                "C-DOC",
                src,
                node.lineno,
                f"public {'class' if is_class else 'function'} `{node.name}` has no docstring",
                "state what it guarantees, not what the body does",
            )


def _mirroring_test(src: SourceFile):
    """C-TEST — a source module with no test at the mirroring path.

    Silent when the project has no test tree at all: reporting "untested" in a
    repo that does not test anything is noise, not a finding.
    """
    root = _project_root(src)
    if root is None:
        return
    tests_root = root / "tests"
    if not tests_root.is_dir():
        return
    if _is_test_file(src, tests_root):
        return
    expected = f"test_{src.path.stem}.py"
    if any(tests_root.rglob(expected)):
        return
    yield _finding(
        "C-TEST",
        src,
        1,
        f"no test named {expected} anywhere under {tests_root.name}/",
        "add the failing test that pins this module's behavior, then make it pass",
    )


def _is_test_file(src: SourceFile, tests_root) -> bool:
    if src.path.name.startswith("test_"):
        return True
    try:
        src.path.resolve().relative_to(tests_root.resolve())
    except ValueError:
        return False
    return True


def _project_root(src: SourceFile):
    for parent in src.path.resolve().parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return None


def _commented_out_code(src: SourceFile):
    """C-DOC — runs of commented-out code, in any language."""
    run_start = None
    run_length = 0
    for number, line in enumerate([*src.lines, ""], start=1):
        if COMMENTED_CODE_RE.match(line):
            run_start = run_start or number
            run_length += 1
            continue
        if run_length >= MIN_COMMENTED_CODE_RUN:
            yield _finding(
                "C-DOC",
                src,
                run_start,
                f"{run_length} lines of commented-out code",
                "delete it; version control already remembers it",
            )
        run_start, run_length = None, 0


def _help_contract(src: SourceFile):
    """C-STRUCT — an entry point that cannot answer --help."""
    if not _is_entry_point(src):
        return
    if "--help" in src.text or "add_help" in src.text:
        return
    yield _finding(
        "C-STRUCT",
        src,
        1,
        "entry point does not handle --help",
        "answer --help in <= 15 lines and exit 0 before reading config or state",
    )


def _is_entry_point(src: SourceFile) -> bool:
    first = src.lines[0] if src.lines else ""
    if first.startswith("#!"):
        return True
    return src.tree is not None and '__name__ == "__main__"' in src.text


def _public_functions(tree):
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and not node.name.startswith("_"):
            yield node


def _is_bare_mapping(annotation) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id in UNTYPED_MAPPINGS
    if isinstance(annotation, ast.Attribute):
        return annotation.attr in UNTYPED_MAPPINGS
    return False


def _finding(
    check: str, src: SourceFile, line: int, message: str, remedy: str
) -> Finding:
    """Every finding from this module is advisory, so severity is not a parameter."""
    return Finding(
        check=check,
        article=ARTICLES[check],
        severity="info",
        path=src.path,
        line=line,
        message=message,
        remedy=remedy,
    )
