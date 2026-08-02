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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PREFIX = "manifest-"
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
        "do",
        "done",
        "echo",
        "elif",
        "else",
        "esac",
        "eval",
        "exit",
        "export",
        "false",
        "fi",
        "for",
        "function",
        "if",
        "in",
        "local",
        "printf",
        "read",
        "return",
        "set",
        "shift",
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
_SHELL_CONTROL = re.compile(r"^(?:if|then|else|elif|fi|for|while|until|do|done|case|esac|in)$")
_SHELL_COMMAND = re.compile(
    r"(?:^|[;|&]\s*|\$\()\s*(?:command\s+)?([A-Za-z_][A-Za-z0-9_.-]*)"
)
_NODE_IMPORT = re.compile(
    r"(?:import\s+(?:[^'\"]+?\s+from\s+)?|require\()['\"]([^'\"]+)['\"]"
)
_OFFLINE_DEGRADATION_IMPORTS = {
    # These SDKs are imported only behind their matching HAS_* capability
    # guards; the parallel-agent runner falls back to a native CLI or returns
    # a surfaced degraded result when the SDK is unavailable.
    "plugins/manifest-workspace/skills/parallel-agent/scripts/agents/runners.py": frozenset({"anthropic"}),
    "plugins/manifest-workspace/skills/parallel-agent/scripts/agents/synthesis.py": frozenset({"anthropic"}),
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
    for contract_path in sorted(plugins.glob(f"{DOMAIN_PREFIX}*/manifest-capabilities.yml")):
        try:
            document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            records.append((contract_path.parent.name, contract_path, {"_error": str(error)}))
            continue
        records.append((contract_path.parent.name, contract_path, document or {}))
    return tuple(records)


def _component_paths(bundle_root: Path, document: dict[str, Any]) -> Iterable[tuple[Path, str]]:
    components = document.get("components", {})
    skills = components.get("skills", {})
    skills_root = bundle_root / str(skills.get("root", "skills"))
    if skills_root.exists():
        yield from ((path, "skills") for path in sorted(skills_root.rglob("SKILL.md")))
    for kind in ("agents", "hooks", "runtime", "guidance"):
        for component in components.get(kind, ()):
            if not isinstance(component, dict) or not isinstance(component.get("path"), str):
                continue
            path = bundle_root / component["path"]
            if path.is_file():
                yield path, kind
            elif path.is_dir():
                yield from (
                    (candidate, kind)
                    for candidate in sorted(path.rglob("*"))
                    if candidate.is_file()
                    and candidate.suffix in _TEXT_SUFFIXES
                )


def _line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def _allowed_native_path(bundle: str, kind: str, text: str) -> bool:
    permitted = set()
    for (allowed_bundle, allowed_kind, _harness), paths in NATIVE_PATH_ALLOWLIST.items():
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
    path: Path, text: str, bundle_root: Path, declared: set[str]
) -> list[Violation]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as error:
        return [
            Violation(path, error.lineno or 1, "invalid-python", "", f"invalid Python: {error.msg}")
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
                (
                    candidate / f"{module}.py"
                ).exists()
                or (candidate / module).is_dir()
                or (candidate / "vendor" / module).is_dir()
                for candidate in (*path.parents, bundle_root, bundle_root / "vendor")
            )
            capability_package = {
                "browser_use": "browser-use",
                "playwright": "playwright",
            }.get(module)
            relative_path = f"plugins/{path.relative_to(bundle_root.parent).as_posix()}"
            explicit_degradation = module in _OFFLINE_DEGRADATION_IMPORTS.get(
                relative_path, frozenset()
            )
            if module and module not in stdlib and not local_package and capability_package not in declared and not explicit_degradation:
                # Optional SDK imports which have an explicit runtime fallback
                # are not a permanent dependency.  The implementation must
                # still raise a visible degraded result when unavailable.
                source_line = text.splitlines()[node.lineno - 1]
                if "try:" in text[: text.find(source_line) + len(source_line)]:
                    continue
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


def _node_import_violations(path: Path, text: str) -> list[Violation]:
    # Dist is already generated and self-contained.  Build inputs may import a
    # package only when its adjacent lockfile pins it exactly.
    if "runtime/dist/" in path.as_posix() or "/templates/" in path.as_posix():
        return []
    lockfile = path.parent / "package-lock.json"
    if not lockfile.exists():
        lockfile = next((parent / "package-lock.json" for parent in path.parents if (parent / "package-lock.json").exists()), None)
    lock_text = lockfile.read_text(encoding="utf-8") if lockfile else ""
    violations: list[Violation] = []
    for match in _NODE_IMPORT.finditer(text):
        imported = match.group(1)
        if imported.startswith((".", "/", "node:")):
            continue
        package = imported.split("/", 1)[0] if not imported.startswith("@") else "/".join(imported.split("/")[:2])
        if f'"node_modules/{package}"' in lock_text:
            continue
        violations.append(
            Violation(path, _line_number(text, match.start(1)), "undeclared-node-dependency", package, f"runtime Node import {package!r} is not lockfile-declared")
        )
    return violations


def _shell_command_violations(path: Path, text: str, declared: set[str]) -> list[Violation]:
    """Check executable probes without treating shell data as commands.

    Shell heredocs frequently embed Python, JSON, and user content.  A regex
    pretending those strings are shell commands causes false dependency
    findings.  The reliable shell dependency seam is ``command -v``: every
    optional executable in the bundled runtimes is probed there.  Direct uses
    of the coordinator/legacy tools are covered by the forbidden-path scan.
    """
    violations: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        probe = re.search(r"\bcommand\s+-v\s+['\"]?([A-Za-z0-9_.-]+)", line)
        if probe is None:
            continue
        command = probe.group(1)
        if command in _SHELL_BUILTINS or command in _POSIX_UTILITIES or command in declared:
            continue
        if command in {"bootstrap.sh", "manifest", "uv", "uvx", "npm", "npx"}:
            violations.append(
                Violation(path, number, "undeclared-shell-dependency", command, f"runtime shell command {command!r} is not contract-declared")
            )
    return violations


def scan(repo_root: Path = ROOT) -> ScanReport:
    """Return all deterministic bundle-runtime violations under ``repo_root``."""
    repo_root = repo_root.resolve()
    violations: list[Violation] = []
    for bundle, contract_path, document in _contract_files(repo_root):
        if "_error" in document:
            violations.append(Violation(contract_path, 1, "invalid-contract", "", document["_error"]))
            continue
        declared = {
            value
            for group in document.get("capabilities", {}).get("executables", {}).values()
            if isinstance(group, list)
            for value in group
            if isinstance(value, str)
        }
        for path, kind in _component_paths(contract_path.parent, document):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            except OSError as error:
                violations.append(Violation(path, 1, "unreadable-runtime", "", str(error)))
                continue
            violations.extend(_path_violations(bundle, kind, path, text))
            if path.suffix == ".py":
                violations.extend(_python_import_violations(path, text, contract_path.parent, declared))
            elif path.suffix in {".mjs", ".js"}:
                violations.extend(_node_import_violations(path, text))
            elif path.suffix == ".sh" or text.startswith("#!") and "sh" in text.splitlines()[0]:
                violations.extend(_shell_command_violations(path, text, declared))
    ordered = tuple(sorted(violations, key=lambda item: (str(item.path), item.line, item.kind, item.value)))
    return ScanReport(ordered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    report = scan(args.repo_root)
    if args.as_json:
        print(json.dumps({"violations": [item.as_json(args.repo_root.resolve()) for item in report.violations]}, indent=2, sort_keys=True))
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
