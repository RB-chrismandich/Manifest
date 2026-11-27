#!/usr/bin/env python3
"""Reject legacy/runtime dependencies from installed domain bundle surfaces.

The coordinator may use bootstrap-era paths while migrating a home.  A released
bundle may not: this gate intentionally starts from each portable contract, then
examines every declared runtime component and every ``SKILL.md`` instruction.
It excludes only top-level ``evals/`` fixture trees, which do not ship as runtime
surfaces; the native-home exception below is a precise Claude hook registration
surface. The observer audit exceptions are occurrence-bound evidence, not a claim
that static scanning proves semantic reachability or call-graph isolation.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
_OBSERVER_BUNDLE = "manifest-workspace"
_OBSERVER_COMPONENT = "native-observer-runtime"
_OBSERVER_RUNTIME = Path("plugins/manifest-workspace/runtime/observer")
_OBSERVER_EVIDENCE = Path("tools/observer_runtime_path_evidence.json")
_OBSERVER_IMPORT_DISTRIBUTIONS = {
    "click": ("click", "8.4.2"),
    "jsonschema": ("jsonschema", "4.26.0"),
    "yaml": ("pyyaml", "6.0.3"),
}
_OBSERVER_VENDORED_POLICY_IMPORTS = frozenset({"manifest_model_policy"})

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
    # manifest-capabilities.yml and no generated Antigravity views, so
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
    # $HOME spellings of the same two trees. Matching is literal substring, so
    # the tilde forms above do not cover these and an adversarial probe walked
    # straight through with `source "$HOME/.claude/scripts/git_ops.sh"`.
    "$home/.claude/scripts",
    "$home/.claude/config",
    "${home}/.claude/scripts",
    "${home}/.claude/config",
    "configs/claude/scripts",
    "configs/claude/config",
    "configs/claude/prompts",
    "configs/claude/references",
    "manifest-agent",
    "uvx --from manifest-agent",
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

# Bundle-relative files whose forbidden-looking text is illustrative rather than
# a runtime dependency.  Keyed by repository-relative path so an exemption can
# never widen to a whole directory by accident.
ILLUSTRATIVE_FILE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # A worked example report that uses bootstrap.sh as its sample subject.
        # The skill never invokes it.
        "plugins/manifest-code-quality/skills/shell-refactor/references/output-format.md",
    }
)

# Generated or third-party artifacts inside a bundle.
_UNSCANNED_DIRS = frozenset({"vendor", "dist", "node_modules", "__pycache__", ".git"})

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
        "sleep",
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
    # PORTABLE_BUNDLES, not DOMAIN_BUNDLES: addon bundles ship too, with
    # generated native views, so their files reach installed harnesses exactly
    # like a domain bundle's. Iterating only the domain set left an addon
    # exempted from the ungoverned-bundle flag yet passed through no scan at
    # all -- the same declared-but-unenforced false green this gate exists to
    # prevent.
    for bundle in PORTABLE_BUNDLES:
        contract_path = plugins / bundle / "manifest-capabilities.yml"
        if not contract_path.is_file():
            records.append(
                (
                    bundle,
                    contract_path,
                    {"_error": "required portable contract is missing"},
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


def _component_paths_declared(
    bundle_root: Path, document: dict[str, Any]
) -> Iterable[tuple[Path, str, str | None]]:
    """Yield only SKILL.md files and explicitly declared component paths."""
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


def _component_paths(
    bundle_root: Path, document: dict[str, Any]
) -> Iterable[tuple[Path, str, str | None]]:
    """Yield every text file the bundle ships, declared or not.

    Declared components and ``SKILL.md`` are not the shipping boundary: the whole
    bundle directory is installed, so a file at an undeclared path runs just as
    readily. Scanning only declarations let such a file carry a legacy
    shared-home reference while this gate reported no violations.
    """
    declared: set[Path] = set()
    for path, kind, component_id in _component_paths_declared(bundle_root, document):
        declared.add(path)
        yield path, kind, component_id
    for candidate in sorted(bundle_root.rglob("*")):
        if not candidate.is_file() or candidate.suffix not in _TEXT_SUFFIXES:
            continue
        if candidate in declared:
            continue
        relative = candidate.relative_to(bundle_root)
        # Eval fixtures describe adversarial inputs; a nested directory named
        # evals in a shipped component remains part of the runtime surface.
        if relative.parts[0] == "evals" or _UNSCANNED_DIRS & set(relative.parts):
            continue
        yield candidate, "undeclared", None


def _line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def _illustrative(path: Path) -> bool:
    """True when a file's forbidden-looking text is a worked example, not a call."""
    try:
        relative = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return relative in ILLUSTRATIVE_FILE_ALLOWLIST


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _observer_evidence(repo_root: Path) -> list[dict[str, Any]]:
    try:
        records = json.loads(
            (repo_root / _OBSERVER_EVIDENCE).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []
    return (
        [record for record in records if isinstance(record, dict)]
        if isinstance(records, list)
        else []
    )


def _migration_occurrence(path: Path, line: int) -> tuple[int, str] | None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_surgical_mixed_cleanup"
            and node.end_lineno is not None
            and node.lineno <= line <= node.end_lineno
        ):
            text = "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])
            return line - node.lineno, _sha256_text(text)
    return None


def _observer_path_exception(
    repo_root: Path, path: Path, pattern: str, line: int, source_line: str
) -> bool:
    """Match one audited observer occurrence, never a file or directory."""
    try:
        relative = path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return False
    migration = relative.endswith("/migration.py")
    anchor = _migration_occurrence(path, line) if migration else None
    if migration and anchor is None:
        return False
    matches = [
        row
        for row in _observer_evidence(repo_root)
        if row.get("path") == relative
        and row.get("kind") == "forbidden-runtime-path"
        and row.get("value") == pattern
        and (
            (row.get("function_offset"), row.get("function_sha256")) == anchor
            if migration
            else row.get("line") == line
        )
    ]
    if len(matches) != 1:
        return False
    row = matches[0]
    actual_line = source_line.rstrip("\r\n")
    if row.get("source_line") != actual_line or row.get("line_sha256") != _sha256_text(
        actual_line
    ):
        return False
    try:
        if relative.startswith(
            "plugins/manifest-workspace/runtime/observer/src/manifest_agent/"
        ):
            source = (
                repo_root
                / "src/manifest_agent"
                / path.relative_to(repo_root / _OBSERVER_RUNTIME / "src/manifest_agent")
            )
        elif relative.startswith(
            "plugins/manifest-workspace/runtime/observer/assets/manifest_agent/_model_policy/"
        ):
            source = (
                repo_root
                / "configs/claude/scripts/manifest_model_policy"
                / path.relative_to(
                    repo_root
                    / _OBSERVER_RUNTIME
                    / "assets/manifest_agent/_model_policy"
                )
            )
        else:
            return False
        if source.read_bytes() != path.read_bytes():
            return False
    except (OSError, ValueError):
        return False
    if not relative.endswith("/migration.py"):
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != matches[0].get(
                "source_sha256"
            ):
                return False
        except OSError:
            return False

    if (
        relative.endswith("/_model_policy/policy_config.py")
        or (relative.endswith("/cli.py") and pattern == "configs/claude/config")
    ) and _observer_dependency_contract(repo_root) is None:
        return False
    return bool(matches[0].get("classification"))


def _observer_dependency_contract(repo_root: Path) -> set[str] | None:
    """Allow only direct imports with exact project pins and matching wheel evidence."""
    runtime = repo_root / _OBSERVER_RUNTIME
    try:
        project = tomllib.loads(
            (runtime / "pyproject.toml").read_text(encoding="utf-8")
        )
        lock = tomllib.loads((runtime / "uv.lock").read_text(encoding="utf-8"))
        proof = json.loads(
            (repo_root / "tools/observer_locked_wheel_evidence.json").read_text(
                encoding="utf-8"
            )
        )
        direct = project["project"]["dependencies"]
        force = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    except (
        OSError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
    ):
        return None
    if (
        not isinstance(project, dict)
        or not isinstance(lock, dict)
        or not isinstance(proof, dict)
        or not isinstance(direct, list)
        or not isinstance(force, dict)
        or not isinstance(lock.get("package"), list)
    ):
        return None
    expected = dict(_OBSERVER_IMPORT_DISTRIBUTIONS.values())
    declared: dict[str, str] = {}
    for requirement in direct:
        if isinstance(requirement, str) and "==" in requirement:
            name, version = requirement.split("==", 1)
            normalized = name.lower().replace("_", "-")
            if normalized in declared:
                return None
            declared[normalized] = version
    if any(declared.get(name) != version for name, version in expected.items()):
        return None
    packages = {
        row.get("name"): row for row in lock.get("package", []) if isinstance(row, dict)
    }
    for name, version in expected.items():
        locked, audited = packages.get(name), proof.get(name)
        if (
            not isinstance(locked, dict)
            or not isinstance(audited, dict)
            or locked.get("version") != version
            or audited.get("version") != version
        ):
            return None
        locked_source, audited_source = locked.get("source"), audited.get("source")
        if (
            not isinstance(locked_source, dict)
            or not isinstance(audited_source, dict)
            or locked_source != audited_source
            or locked_source.get("registry") != "https://pypi.org/simple"
        ):
            return None
        locked_wheels, audited_wheels = locked.get("wheels"), audited.get("wheels")
        if (
            not isinstance(locked_wheels, list)
            or not isinstance(audited_wheels, list)
            or not locked_wheels
            or any(
                not isinstance(row, dict) for row in (*locked_wheels, *audited_wheels)
            )
        ):
            return None
        locked_pairs = {(row.get("url"), row.get("hash")) for row in locked_wheels}
        audited_pairs = {(row.get("url"), row.get("hash")) for row in audited_wheels}
        if locked_pairs != audited_pairs or len(locked_pairs) != len(locked_wheels):
            return None
        if any(
            not str(row.get("hash", "")).startswith("sha256:") for row in locked_wheels
        ):
            return None
    overlay = runtime / "assets/manifest_agent/_model_policy"
    required_policy_files = frozenset(
        {
            "__init__.py",
            "controller.py",
            "failures.py",
            "frontmatter.py",
            "headless.py",
            "policy_config.py",
            "resolver.py",
            "skill_command.py",
            "skill_execution.py",
            "skill_process.py",
            "skill_recovery.py",
            "skill_run.py",
        }
    )
    modules = {path.name: path for path in overlay.glob("*.py")}
    if set(modules) != required_policy_files or any(
        force.get(f"assets/manifest_agent/_model_policy/{name}")
        != f"manifest_agent/_model_policy/{name}"
        for name in required_policy_files
    ):
        return None
    canonical_policy = repo_root / "configs/claude/scripts/manifest_model_policy"
    for name, path in modules.items():
        try:
            if (canonical_policy / name).read_bytes() != path.read_bytes():
                return None
        except OSError:
            return None
    for relative, snippet in (
        (
            "src/manifest_agent/skill_run.py",
            "from manifest_agent._model_policy.skill_run import",
        ),
        (
            "src/manifest_agent/plugin_view_renderers.py",
            "from manifest_agent._model_policy import",
        ),
    ):
        try:
            source = (runtime / relative).read_text(encoding="utf-8")
        except OSError:
            return None
        guard = (
            "except ModuleNotFoundError as error:\n"
            '    if error.name != "manifest_agent._model_policy":\n'
            "        raise\n"
        )
        if snippet not in source or guard not in source:
            return None
    return set(_OBSERVER_IMPORT_DISTRIBUTIONS) | set(_OBSERVER_VENDORED_POLICY_IMPORTS)


def _is_observer_runtime_path(
    repo_root: Path, path: Path, bundle: str, component_id: str | None
) -> bool:
    if bundle != _OBSERVER_BUNDLE or component_id != _OBSERVER_COMPONENT:
        return False
    try:
        path.resolve().relative_to((repo_root / _OBSERVER_RUNTIME).resolve())
        return True
    except ValueError:
        return False


def _path_violations(
    bundle: str,
    kind: str,
    path: Path,
    text: str,
    repo_root: Path = ROOT,
    component_id: str | None = None,
) -> list[Violation]:
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
            line = _line_number(text, position)
            source_line = text.splitlines(keepends=True)[line - 1]
            observer_exception = (
                bundle == _OBSERVER_BUNDLE
                and component_id == _OBSERVER_COMPONENT
                and path.resolve().is_relative_to(
                    (repo_root / _OBSERVER_RUNTIME).resolve()
                )
                and _observer_path_exception(
                    repo_root, path, matched, line, source_line
                )
            )
            if (
                not _allowed_native_path(bundle, kind, matched)
                and not _illustrative(path)
                and not observer_exception
            ):
                violations.append(
                    Violation(
                        path,
                        line,
                        "forbidden-runtime-path",
                        matched,
                        f"{bundle} {kind} depends on forbidden runtime path {matched!r}",
                    )
                )
            start = position + len(pattern)
    return violations


def _observer_import_exception(
    repo_root: Path, path: Path, module: str, line: int
) -> bool:
    try:
        relative = path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return False
    rows = [
        row
        for row in _observer_evidence(repo_root)
        if row.get("kind") == "undeclared-python-dependency"
        and row.get("path") == relative
        and row.get("value") == module
        and row.get("line") == line
    ]
    if len(rows) != 1:
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    line_imports = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)) or node.lineno != line:
            continue
        if isinstance(node, ast.Import):
            line_imports += sum(
                alias.name.split(".", 1)[0] == module for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            line_imports += int(node.module.split(".", 1)[0] == module)
    if line_imports != len(rows):
        return False

    source_line = path.read_text(encoding="utf-8").splitlines()[line - 1]
    if rows[0].get("source_line") != source_line or rows[0].get(
        "line_sha256"
    ) != _sha256_text(source_line):
        return False
    if not relative.endswith("/migration.py") and hashlib.sha256(
        path.read_bytes()
    ).hexdigest() != rows[0].get("source_sha256"):
        return False
    if relative.startswith(
        "plugins/manifest-workspace/runtime/observer/src/manifest_agent/"
    ):
        source = (
            repo_root
            / "src/manifest_agent"
            / path.relative_to(repo_root / _OBSERVER_RUNTIME / "src/manifest_agent")
        )
    elif relative.startswith(
        "plugins/manifest-workspace/runtime/observer/assets/manifest_agent/_model_policy/"
    ):
        source = (
            repo_root
            / "configs/claude/scripts/manifest_model_policy"
            / path.relative_to(
                repo_root / _OBSERVER_RUNTIME / "assets/manifest_agent/_model_policy"
            )
        )
    else:
        return False
    try:
        return source.read_bytes() == path.read_bytes()
    except OSError:
        return False


@dataclass(frozen=True)
class _BundleScan:
    repo_root: Path
    name: str
    root: Path
    declared: set[str]
    observer_imports: set[str] | None


def _python_import_sites(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (
                (node.lineno, alias.name.split(".", 1)[0]) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.split(".", 1)[0]


def _declared_python_import(
    path: Path, line: int, module: str, component_id: str | None, context: _BundleScan
) -> bool:
    if module in sys.stdlib_module_names:
        return True
    if any(
        (candidate / f"{module}.py").exists()
        or (candidate / module).is_dir()
        or (candidate / "vendor" / module).is_dir()
        for candidate in (*path.parents, context.root, context.root / "vendor")
    ):
        return True
    capability = {"browser_use": "browser-use", "playwright": "playwright"}.get(module)
    if capability in context.declared or module in _COMPONENT_DEGRADATION_IMPORTS.get(
        (context.name, component_id), frozenset()
    ):
        return True
    return (
        context.observer_imports is not None
        and module in context.observer_imports
        and _is_observer_runtime_path(
            context.repo_root, path, context.name, component_id
        )
        and _observer_import_exception(context.repo_root, path, module, line)
    )


def _python_import_violations(
    path: Path,
    text: str,
    component_id: str | None,
    context: _BundleScan,
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
    return [
        Violation(
            path,
            line,
            "undeclared-python-dependency",
            module,
            f"runtime Python import {module!r} is neither stdlib nor bundle-vendored",
        )
        for line, module in _python_import_sites(tree)
        if not _declared_python_import(path, line, module, component_id, context)
    ]


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
    harness_commands = {"claude", "codex", "cursor-agent", "agy", "devin"}
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


def _component_shell_functions(
    paths: tuple[tuple[Path, str, str | None], ...],
) -> set[str]:
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
    return component_functions


def _scan_bundle(
    repo_root: Path, bundle: str, contract_path: Path, document: dict[str, Any]
) -> list[Violation]:
    violations: list[Violation] = []
    declared = {
        value
        for group in document.get("capabilities", {}).get("executables", {}).values()
        if isinstance(group, list)
        for value in group
        if isinstance(value, str)
    }
    paths = tuple(_component_paths(contract_path.parent, document))
    has_observer = bundle == _OBSERVER_BUNDLE and any(
        item.get("id") == _OBSERVER_COMPONENT
        for item in document.get("components", {}).get("runtime", [])
        if isinstance(item, dict)
    )
    observer_imports = (
        _observer_dependency_contract(repo_root) if has_observer else None
    )
    if has_observer and observer_imports is None:
        violations.append(
            Violation(
                repo_root / _OBSERVER_RUNTIME / "pyproject.toml",
                1,
                "invalid-observer-dependency-contract",
                "",
                "observer direct pins, lock wheel evidence, vendored policy force-includes, or internal-first fallback changed",
            )
        )
    context = _BundleScan(
        repo_root, bundle, contract_path.parent, declared, observer_imports
    )
    violations.extend(_scan_component_files(context, paths))
    return violations


def _scan_component_files(
    context: _BundleScan,
    paths: tuple[tuple[Path, str, str | None], ...],
) -> list[Violation]:
    violations: list[Violation] = []
    component_functions = _component_shell_functions(paths)
    for path, kind, component_id in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as error:
            violations.append(Violation(path, 1, "unreadable-runtime", "", str(error)))
            continue
        violations.extend(
            _path_violations(
                context.name, kind, path, text, context.repo_root, component_id
            )
        )
        # Undeclared files are swept only for forbidden runtime paths. The
        # dependency checks below are contract-conformance checks and are
        # meaningful only for what the contract actually declares; running
        # them over every shipped file would report undeclared imports for
        # bundle tests and helper scripts that were never contract surfaces.
        if kind == "undeclared":
            continue
        if path.suffix == ".py":
            violations.extend(
                _python_import_violations(path, text, component_id, context)
            )
        elif path.suffix in {".mjs", ".js"}:
            violations.extend(
                _node_import_violations(path, text, context.name, component_id)
            )
        elif path.suffix == ".sh" or (
            text.startswith("#!") and "sh" in text.splitlines()[0]
        ):
            violations.extend(
                _shell_command_violations(
                    path, text, context.declared, component_functions
                )
            )
    return violations


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
        violations.extend(_scan_bundle(repo_root, bundle, contract_path, document))
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
