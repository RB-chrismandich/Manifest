#!/usr/bin/env python3
"""Reject legacy/runtime dependencies from installed domain bundle surfaces.

The coordinator may use bootstrap-era paths while migrating a home.  A released
bundle may not: this gate intentionally starts from each portable contract, then
examines every declared runtime component and every ``SKILL.md`` instruction.
It does not suppress whole trees; the only native-home exception is the precise
Claude hook settings file below, which is a harness-owned registration surface.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_BUNDLES = (
    "manifest-code-quality",
    "manifest-docs",
    "manifest-forge",
    "manifest-ops",
    "manifest-security",
    "manifest-spec-planning",
    "manifest-workspace",
    "stitch-design",
)
ADDON_BUNDLES = ("manifest-i-have-adhd",)
PORTABLE_BUNDLES = (*DOMAIN_BUNDLES, *ADDON_BUNDLES)

# Bundles deliberately outside the portable-contract system.  Empty by design:
# an entry here means the bundle ships to Claude only, is installed by no
# harness adapter, and is scanned by no gate, so each one needs a recorded
# reason and an owner.  Prefer giving the bundle a contract over adding it here.
UNGOVERNED_BUNDLES: dict[str, str] = {
    # Ships in the marketplace and installs under Claude Code, but has no
    # manifest-capabilities.yml and no generated Gemini/Antigravity views, so
    # no harness adapter can install it and delegation is Claude-only in
    # practice.  Recorded here so the gap is declared rather than invisible.
    # Removing this entry is the fix tracked by issue #784 (delegation setup
    # for Cursor and Devin): give the bundle a portable contract and add it to
    # ADDON_BUNDLES.
    "manifest-delegate": "no portable contract; Claude-only (issue #784)",
}

FORBIDDEN_RUNTIME_PATTERNS = (
    "bootstrap.sh",
    "bootstrap/",
    "~/.claude/scripts",
    "~/.claude/config",
    "configs/claude/scripts",
    "configs/claude/config",
    "configs/claude/prompts",
    "configs/claude/references",
    "manifest-agent",
    "uvx --from manifest-agent",
    "manifest parallel-agent",
    "manifest smoke",
    "../manifest-",
    "npx skills add",
    "stitch-skills/plugins",
    "stitch-utilities",
)

# This is purposefully a single file-level exception rather than a directory
# exemption.  It is valid only in Claude hook metadata; all other cross-home
# paths remain forbidden.
NATIVE_PATH_ALLOWLIST: dict[tuple[str, str, str], frozenset[str]] = {
    ("manifest-workspace", "hooks", "claude"): frozenset({"~/.claude/settings.json"}),
}

_TEXT_SUFFIXES = {".md", ".json", ".py", ".sh", ".mjs", ".js", ".yml", ".yaml"}
_SHELL_BUILTINS = frozenset(
    {
        ".",
        ":",
        "alias",
        "break",
        "case",
        "cd",
        "command",
        "continue",
        "declare",
        "do",
        "done",
        "echo",
        "elif",
        "else",
        "esac",
        "eval",
        "exec",
        "exit",
        "export",
        "false",
        "fi",
        "for",
        "function",
        "if",
        "in",
        "local",
        "mapfile",
        "printf",
        "read",
        "readarray",
        "readonly",
        "return",
        "set",
        "shift",
        "shopt",
        "source",
        "test",
        "then",
        "time",
        "trap",
        "true",
        "type",
        "ulimit",
        "umask",
        "unalias",
        "unset",
        "until",
        "while",
        "[[",
        "[",
    }
)
_POSIX_UTILITIES = frozenset(
    {
        "awk",
        "basename",
        "cat",
        "chmod",
        "cmp",
        "cp",
        "cut",
        "date",
        "dirname",
        "env",
        "find",
        "grep",
        "head",
        "ln",
        "mkdir",
        "mktemp",
        "mv",
        "pwd",
        "rm",
        "rmdir",
        "sed",
        "sort",
        "tail",
        "tee",
        "touch",
        "tr",
        "uname",
        "wc",
        "xargs",
    }
)
_SHELL_CONTROL = re.compile(
    r"^(?:if|then|else|elif|fi|for|while|until|do|done|case|esac|in)$"
)
_SHELL_COMMAND = re.compile(
    r"(?:^|[;|&]\s*|\$\()\s*(?:command\s+)?([A-Za-z_][A-Za-z0-9_.-]*)"
)
_NODE_IMPORT = re.compile(
    r"(?:import\s+(?:[^'\"]+?\s+from\s+)?|require\()['\"]([^'\"]+)['\"]"
)
_COMPONENT_DEGRADATION_IMPORTS = {
    # The parallel-agent component deliberately supports native-CLI fallback
    # when an SDK or Rich rendering is unavailable.  This exception is scoped
    # to the declared component, never a bundle directory.
    ("manifest-workspace", "parallel-agent-scripts"): frozenset(
        {"anthropic", "google", "rich"}
    ),
    ("manifest-ops", "ops-bin"): frozenset({"yaml"}),
}
_COMPONENT_NODE_DEPENDENCIES = {
    # This is a generated-project template, not a dependency of Manifest's
    # installed runtime.  The exact scaffold component declares the two
    # project dependencies in its adjacent package manifest.
    ("manifest-code-quality", "scaffold-templates"): frozenset(
        {"@eslint/js", "typescript-eslint"}
    ),
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    kind: str
    value: str
    message: str

    def as_json(self, root: Path) -> dict[str, Any]:
        item = asdict(self)
        try:
            item["path"] = str(self.path.relative_to(root))
        except ValueError:
            item["path"] = str(self.path)
        return item


@dataclass(frozen=True)
class ScanReport:
    violations: tuple[Violation, ...]


def _contract_files(repo_root: Path) -> Iterable[tuple[str, Path, dict[str, Any]]]:
    plugins = repo_root / "plugins"
    if not plugins.exists():
        return ()
    records = []
    for bundle in DOMAIN_BUNDLES:
        contract_path = plugins / bundle / "manifest-capabilities.yml"
        if not contract_path.is_file():
            records.append(
                (
                    bundle,
                    contract_path,
                    {"_error": "required domain contract is missing"},
                )
            )
            continue
        try:
            document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            records.append(
                (contract_path.parent.name, contract_path, {"_error": str(error)})
            )
            continue
        records.append((contract_path.parent.name, contract_path, document or {}))
    return tuple(records)


def _component_paths(
    bundle_root: Path, document: dict[str, Any]
) -> Iterable[tuple[Path, str, str | None]]:
    components = document.get("components", {})
    skills = components.get("skills", {})
    skills_root = bundle_root / str(skills.get("root", "skills"))
    if skills_root.exists():
        yield from (
            (path, "skills", path.parent.name)
            for path in sorted(skills_root.rglob("SKILL.md"))
        )
    for kind in ("agents", "hooks", "runtime", "guidance"):
        for component in components.get(kind, ()):
            if not isinstance(component, dict) or not isinstance(
                component.get("path"), str
            ):
                continue
            path = bundle_root / component["path"]
            if path.is_file():
                yield path, kind, component.get("id")
            elif path.is_dir():
                yield from (
                    (candidate, kind, component.get("id"))
                    for candidate in sorted(path.rglob("*"))
                    if candidate.is_file() and candidate.suffix in _TEXT_SUFFIXES
                )


def _line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def _allowed_native_path(bundle: str, kind: str, text: str) -> bool:
    permitted = set()
    for (
        allowed_bundle,
        allowed_kind,
        _harness,
    ), paths in NATIVE_PATH_ALLOWLIST.items():
        if bundle == allowed_bundle and kind == allowed_kind:
            permitted.update(paths)
    return text in permitted


def _path_violations(bundle: str, kind: str, path: Path, text: str) -> list[Violation]:
    violations: list[Violation] = []
    lowered = text.lower()
    for pattern in FORBIDDEN_RUNTIME_PATTERNS:
        if pattern not in lowered:
            continue
        start = 0
        while True:
            position = lowered.find(pattern, start)
            if position < 0:
                break
            matched = text[position : position + len(pattern)]
            if not _allowed_native_path(bundle, kind, matched):
                violations.append(
                    Violation(
                        path,
                        _line_number(text, position),
                        "forbidden-runtime-path",
                        matched,
                        f"{bundle} {kind} depends on forbidden runtime path {matched!r}",
                    )
                )
            start = position + len(pattern)
    return violations


def _python_import_violations(
    path: Path,
    text: str,
    bundle: str,
    bundle_root: Path,
    component_id: str | None,
    declared: set[str],
) -> list[Violation]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as error:
        return [
            Violation(
                path,
                error.lineno or 1,
                "invalid-python",
                "",
                f"invalid Python: {error.msg}",
            )
        ]
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    violations: list[Violation] = []
    for node in ast.walk(tree):
        module = ""
        level = 0
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module else []
            level = node.level
        else:
            continue
        if level:
            continue
        for imported in names:
            module = (imported or "").split(".", 1)[0]
            local_package = any(
                (candidate / f"{module}.py").exists()
                or (candidate / module).is_dir()
                or (candidate / "vendor" / module).is_dir()
                for candidate in (*path.parents, bundle_root, bundle_root / "vendor")
            )
            capability_package = {
                "browser_use": "browser-use",
                "playwright": "playwright",
            }.get(module)
            explicit_degradation = module in _COMPONENT_DEGRADATION_IMPORTS.get(
                (bundle, component_id), frozenset()
            )
            if (
                module
                and module not in stdlib
                and not local_package
                and capability_package not in declared
                and not explicit_degradation
            ):
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "undeclared-python-dependency",
                        module,
                        f"runtime Python import {module!r} is neither stdlib nor bundle-vendored",
                    )
                )
    return violations


def _node_import_violations(
    path: Path, text: str, bundle: str, component_id: str | None
) -> list[Violation]:
    # Dist is already generated and self-contained.  Build inputs may import a
    # package only when its adjacent lockfile pins it exactly.
    lockfile = path.parent / "package-lock.json"
    if not lockfile.exists():
        lockfile = next(
            (
                parent / "package-lock.json"
                for parent in path.parents
                if (parent / "package-lock.json").exists()
            ),
            None,
        )
    lock_text = lockfile.read_text(encoding="utf-8") if lockfile else ""
    violations: list[Violation] = []
    for match in _NODE_IMPORT.finditer(text):
        imported = match.group(1)
        if imported.startswith((".", "/", "node:")):
            continue
        package = (
            imported.split("/", 1)[0]
            if not imported.startswith("@")
            else "/".join(imported.split("/")[:2])
        )
        if (
            f'"node_modules/{package}"' in lock_text
            or package
            in _COMPONENT_NODE_DEPENDENCIES.get((bundle, component_id), frozenset())
        ):
            continue
        violations.append(
            Violation(
                path,
                _line_number(text, match.start(1)),
                "undeclared-node-dependency",
                package,
                f"runtime Node import {package!r} is not lockfile-declared",
            )
        )
    return violations


def _shell_command_violations(
    path: Path,
    text: str,
    declared: set[str],
    component_functions: set[str],
) -> list[Violation]:
    """Require every direct shell executable to be declared or a shell builtin.

    This intentionally does not use a command-name allowlist. A new executable
    is a runtime dependency even when the checker has never heard of it.
    """
    violations: list[Violation] = []
    local_functions = set(
        re.findall(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_-]*)\s*\(\)", text, re.M)
    )
    local_functions.update(component_functions)
    harness_commands = {"claude", "codex", "gemini", "cursor-agent", "agy", "devin"}
    heredoc: str | None = None
    quoted_assignment = False
    inline_python = False
    double_quoted_python = False
    double_quoted_message = False
    case_depth = 0

    def unclosed_quote(value: str) -> str | None:
        # Shell snippets often embed Python through a multi-line quoted -c
        # argument.  Its body is data, not a sequence of shell commands.
        for quote in ('"', "'"):
            if value.count(quote) % 2:
                return quote
        return None

    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if quoted_assignment:
            if stripped.endswith("'"):
                quoted_assignment = False
            continue
        if heredoc:
            if stripped == heredoc:
                heredoc = None
            continue
        if inline_python:
            if "'" in stripped:
                inline_python = False
            continue
        if double_quoted_python:
            if stripped.startswith('"'):
                double_quoted_python = False
            continue
        if double_quoted_message:
            if re.search(r"(?<!\\)\"$", stripped):
                double_quoted_message = False
            continue
        marker = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if marker:
            heredoc = marker.group(1)
        if not stripped or stripped.startswith("#"):
            continue
        # A single-quoted ``python -c`` payload can span many lines. Its body
        # is not shell syntax, even when it contains words that look like
        # commands. Shell cannot contain an unescaped single quote in that
        # payload, so the next quote ends it.
        inline = re.search(r"(?:^|\s)-c\s+'", stripped)
        if inline:
            payload = stripped[inline.end() :]
            inline_python = "'" not in payload
            continue
        if re.search(r"(?:^|\s)-c\s+\"$", stripped):
            double_quoted_python = True
            continue
        if re.search(r"\bcase\s+.+\s+in\b", stripped) and "esac" in stripped:
            continue
        if re.match(r"^case\s+.+\s+in", stripped):
            if "esac" not in stripped:
                case_depth += 1
            continue
        if case_depth:
            if stripped.startswith("esac"):
                case_depth -= 1
                continue
            pattern = re.match(
                r"^(?:[A-Za-z0-9_*.-]+(?:\s*\|\s*[A-Za-z0-9_*.-]+)*)\)\s*(.*)$",
                stripped,
            )
            if pattern is None:
                continue
            stripped = pattern.group(1)
            if not stripped:
                continue
            if re.match(r"['\"]?\$", stripped):
                continue
        if re.match(
            r"^(?:(?:local|readonly|declare)\s+)?[A-Za-z_][A-Za-z0-9_]*='", stripped
        ):
            quoted_assignment = unclosed_quote(stripped) == "'"
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", stripped):
            continue
        if re.search(r"\b(?:error|err)\s+\"[^\"]*$", stripped):
            double_quoted_message = True
            continue
        if stripped.startswith("for (("):
            continue
        # Do not split control syntax or quoted messages. Splitting only the
        # quote-stripped form finds pipeline and boolean-chain command heads
        # without mistaking their arguments for executables.
        if re.match(
            r"^(?:(?:if|then|else|elif|do|while|until)\s+|!\s*)*"
            r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*['\"]?\$",
            stripped,
        ):
            continue
        unquoted = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "", stripped)
        for segment in re.split(r";|&&|\|\||(?<!\|)\|(?!\|)", unquoted):
            if segment.lstrip().startswith("for "):
                continue
            candidate = re.sub(
                r"^(?:(?:if|then|else|elif|do|while|until)\s+|!\s*)+",
                "",
                segment.strip(),
            )
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", candidate):
                continue
            if candidate.startswith(("for ", "for ((")):
                continue
            candidate = re.sub(r"^[^\s)]*\)\s*", "", candidate)
            candidate = re.sub(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)+", "", candidate)
            if candidate.endswith(")") and re.fullmatch(
                r"\*|[A-Za-z0-9_.-]+\)?", candidate
            ):
                continue
            probe = re.match(r"command\s+-v\s+['\"]?([A-Za-z0-9_.-]+)", candidate)
            direct = re.match(r"([A-Za-z_][A-Za-z0-9_.-]*)", candidate)
            command = probe.group(1) if probe else direct.group(1) if direct else ""
            if direct and candidate[direct.end() :].lstrip().startswith(("=", "+=")):
                continue
            if (
                not command
                or command in _SHELL_BUILTINS
                or command in _POSIX_UTILITIES
                or command in declared
                or command in harness_commands
                or command in local_functions
            ):
                continue
            violations.append(
                Violation(
                    path,
                    number,
                    "undeclared-shell-dependency",
                    command,
                    f"runtime shell command {command!r} is not contract-declared",
                )
            )
    return violations


def _ungoverned_bundles(repo_root: Path) -> tuple[Violation, ...]:
    """Flag any ``plugins/`` directory outside the portable-contract system.

    Coverage is opt-out, not opt-in.  A bundle added to ``plugins/`` without a
    portable contract is enumerated by no adapter and scanned by no gate, so it
    reports clean no matter what it contains -- the false green that section 10
    of the bootstrap-free distribution design forbids.
    """
    plugins = repo_root / "plugins"
    if not plugins.is_dir():
        return ()
    found: list[Violation] = []
    for entry in sorted(plugins.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in PORTABLE_BUNDLES or entry.name in UNGOVERNED_BUNDLES:
            continue
        found.append(
            Violation(
                entry,
                1,
                "ungoverned-bundle",
                entry.name,
                f"{entry.name} is under plugins/ but appears in neither "
                "DOMAIN_BUNDLES nor ADDON_BUNDLES, so no harness adapter "
                "installs it and no runtime-path gate scans it",
            )
        )
    return tuple(found)


def scan(repo_root: Path = ROOT) -> ScanReport:
    """Return all deterministic bundle-runtime violations under ``repo_root``."""
    repo_root = repo_root.resolve()
    violations: list[Violation] = list(_ungoverned_bundles(repo_root))
    for bundle, contract_path, document in _contract_files(repo_root):
        if "_error" in document:
            violations.append(
                Violation(contract_path, 1, "invalid-contract", "", document["_error"])
            )
            continue
        declared = {
            value
            for group in document.get("capabilities", {})
            .get("executables", {})
            .values()
            if isinstance(group, list)
            for value in group
            if isinstance(value, str)
        }
        paths = tuple(_component_paths(contract_path.parent, document))
        component_functions: set[str] = set()
        for candidate, _kind, _component_id in paths:
            if candidate.suffix != ".sh":
                continue
            try:
                component_functions.update(
                    re.findall(
                        r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_-]*)\s*\(\)",
                        candidate.read_text(encoding="utf-8"),
                        re.M,
                    )
                )
            except (OSError, UnicodeDecodeError):
                continue
        for path, kind, component_id in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            except OSError as error:
                violations.append(
                    Violation(path, 1, "unreadable-runtime", "", str(error))
                )
                continue
            violations.extend(_path_violations(bundle, kind, path, text))
            if path.suffix == ".py":
                violations.extend(
                    _python_import_violations(
                        path,
                        text,
                        bundle,
                        contract_path.parent,
                        component_id,
                        declared,
                    )
                )
            elif path.suffix in {".mjs", ".js"}:
                violations.extend(
                    _node_import_violations(path, text, bundle, component_id)
                )
            elif path.suffix == ".sh" or (
                text.startswith("#!") and "sh" in text.splitlines()[0]
            ):
                violations.extend(
                    _shell_command_violations(path, text, declared, component_functions)
                )
    ordered = tuple(
        sorted(
            violations,
            key=lambda item: (str(item.path), item.line, item.kind, item.value),
        )
    )
    return ScanReport(ordered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    report = scan(args.repo_root)
    if args.as_json:
        print(
            json.dumps(
                {
                    "violations": [
                        item.as_json(args.repo_root.resolve())
                        for item in report.violations
                    ]
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for violation in report.violations:
            try:
                display = violation.path.relative_to(args.repo_root.resolve())
            except ValueError:
                display = violation.path
            print(f"{display}:{violation.line}: {violation.kind}: {violation.message}")
    return 1 if report.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
