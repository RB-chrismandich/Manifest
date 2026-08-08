"""C-DANGER (CON-013) — evaluators, unsafe deserializers, shells, built queries.

The distinguishing rule for every match here is *who chose the string*. A
constant statement is fine; the same call with a formatted string is the defect.
So each detector below tests the shape of the ARGUMENT, not just the callee —
`cur.execute("SELECT 1")` must stay silent while `cur.execute(f"...{name}")`
must not, or the check is a blanket ban on database access.
"""

from __future__ import annotations

import ast
import re

from ..findings import Finding
from ..registry import Registry
from ..source import SourceFile

CHECK = "C-DANGER"
ARTICLE = "CON-013"

# name -> (what it does, the safe counterpart)
EVALUATORS = {
    "eval": ("evaluates arbitrary source", "use ast.literal_eval, or a real parser"),
    "exec": ("executes arbitrary source", "call the function you mean directly"),
}

DESERIALIZERS = {
    ("pickle", "load"),
    ("pickle", "loads"),
    ("cPickle", "load"),
    ("cPickle", "loads"),
    ("dill", "load"),
    ("dill", "loads"),
    ("cloudpickle", "load"),
    ("cloudpickle", "loads"),
    ("marshal", "load"),
    ("marshal", "loads"),
    ("shelve", "open"),
}

SHELL_CALLS = {("os", "system"), ("os", "popen")}

CURSOR_METHODS = {"execute", "executemany", "executescript"}

# Loader names that make yaml.load safe. Anything else (or nothing) is not.
SAFE_YAML_LOADERS = {"SafeLoader", "CSafeLoader", "BaseLoader"}

# Line-based patterns for languages we do not parse. Deliberately narrow: each
# one is a construct with no safe reading, not merely a suspicious substring.
LINE_PATTERNS = {
    "shell": [
        (
            re.compile(r"^\s*eval\s+[\"'$]"),
            "shell `eval` on a variable",
            "use a case statement or an array",
        ),
        (
            re.compile(r"\b(curl|wget|fetch)\b.*\|\s*(sudo\s+)?(sh|bash)\b"),
            "piping a download into a shell",
            "download, verify a checksum, then run",
        ),
    ],
    "node": [
        (
            re.compile(r"(?<![.\w])eval\s*\("),
            "eval() evaluates arbitrary source",
            "use JSON.parse, or a real parser",
        ),
        (
            re.compile(r"new\s+Function\s*\("),
            "new Function() compiles arbitrary source",
            "call the function you mean directly",
        ),
    ],
    "go": [
        (
            re.compile(r'exec\.Command\(\s*"(sh|bash)"\s*,\s*"-c"'),
            "shelling out to sh -c",
            "exec.Command with the program and its argv",
        ),
    ],
}


def run(src: SourceFile, registry: Registry) -> list[Finding]:
    """Report dangerous operations and injectable string-building (CON-013)."""
    if src.language is None:
        return []
    if src.tree is not None:
        return list(_python(src))
    return list(_line_based(src))


def _python(src: SourceFile):
    for node in ast.walk(src.tree):
        if not isinstance(node, ast.Call):
            continue
        yield from _evaluator(src, node)
        yield from _deserializer(src, node)
        yield from _shell(src, node)
        yield from _query(src, node)


def _evaluator(src: SourceFile, node: ast.Call):
    # A bare Name only: `ast.literal_eval` is an Attribute and is the fix, not the defect.
    if isinstance(node.func, ast.Name) and node.func.id in EVALUATORS:
        what, remedy = EVALUATORS[node.func.id]
        yield _finding(src, node.lineno, f"`{node.func.id}()` {what}", remedy)


def _deserializer(src: SourceFile, node: ast.Call):
    pair = _dotted(node.func)
    if pair in DESERIALIZERS:
        module, attr = pair
        yield _finding(
            src,
            node.lineno,
            f"`{module}.{attr}()` reconstructs arbitrary objects from its input",
            "use json, or a schema-validated decoder that builds only declared types",
        )
        return
    if pair == ("yaml", "load") and not _has_safe_loader(node):
        yield _finding(
            src,
            node.lineno,
            "`yaml.load()` without a safe loader constructs arbitrary Python objects",
            "use yaml.safe_load, or pass Loader=yaml.SafeLoader",
        )


def _shell(src: SourceFile, node: ast.Call):
    pair = _dotted(node.func)
    if pair in SHELL_CALLS:
        module, attr = pair
        yield _finding(
            src,
            node.lineno,
            f"`{module}.{attr}()` runs its argument through a shell",
            "subprocess.run([...]) with the program and its arguments as a list",
        )
        return
    for keyword in node.keywords:
        if keyword.arg == "shell" and _is_true(keyword.value):
            yield _finding(
                src,
                node.lineno,
                "`shell=True` makes every metacharacter in the command executable",
                "drop shell=True and pass the command as a list of arguments",
            )


def _query(src: SourceFile, node: ast.Call):
    """A cursor call whose statement was assembled rather than written."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in CURSOR_METHODS:
        return
    if not node.args or not _is_built_string(node.args[0]):
        return
    yield _finding(
        src,
        node.lineno,
        f"`{node.func.attr}()` is given a statement built by string formatting",
        "keep the statement constant and pass the values as bound parameters",
    )


def _is_built_string(node) -> bool:
    """True for f-strings, %, +, and .format() — the four ways to inject."""
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"format", "join"}
    )


def _has_safe_loader(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "Loader":
            name = _dotted(keyword.value)
            tail = name[1] if name else getattr(keyword.value, "id", "")
            return tail in SAFE_YAML_LOADERS
    return False


def _is_true(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _dotted(node) -> tuple[str, str] | None:
    """('pickle', 'loads') for pickle.loads, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return (node.value.id, node.attr)
    return None


def _line_based(src: SourceFile):
    patterns = LINE_PATTERNS.get(src.language.key, [])
    if not patterns:
        return
    prefix = src.language.comment_prefix
    for number, line in enumerate(src.lines, start=1):
        if line.lstrip().startswith(prefix):
            continue
        for pattern, message, remedy in patterns:
            if pattern.search(line):
                yield _finding(src, number, message, remedy)


def _finding(src: SourceFile, line: int, message: str, remedy: str) -> Finding:
    return Finding(
        check=CHECK,
        article=ARTICLE,
        severity="error",
        path=src.path,
        line=line,
        message=message,
        remedy=remedy,
    )
