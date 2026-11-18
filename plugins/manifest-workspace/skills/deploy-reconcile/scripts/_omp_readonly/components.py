"""Observe skills through OMP's read-only discovery CLI, not bundle declarations.

OMP 18.20.0: `omp skill list --json` emits {skills, warnings}; rows contain
name, filePath, baseDir, source, hide (src/cli/skill-list.ts). See OMP's
skills.md: discovery can filter, rename, or deduplicate installed skills.
A discovered skill proves fresh-process discovery, not active-session activation.
"""

from __future__ import annotations

import json
from pathlib import Path

from .inventory import OmpInventoryError, regular_chain
from .models import NativeComponentInspection


def _attribute_skill_rows(rows, roots):
    records, seen, attributed = [], set(), set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or any(
                not isinstance(row.get(field), str) or not row[field]
                for field in ("name", "filePath", "baseDir", "source")
            )
            or not isinstance(row.get("hide"), bool)
        ):
            raise OmpInventoryError("OMP skill inventory row is malformed")
        path, base = Path(row["filePath"]), Path(row["baseDir"])
        if not path.is_absolute() or not base.is_absolute() or path.parent != base:
            raise OmpInventoryError("OMP skill inventory path is malformed")
        owners = [root for root in roots if path.is_relative_to(root)]
        if not owners:
            # Other native/foreign providers are not evidence for owned plugins.
            continue
        if len(owners) != 1 or path in seen:
            raise OmpInventoryError("OMP skill inventory attribution is ambiguous")
        root = owners[0]
        package = roots[root]
        if row["source"] not in {"claude-plugins:user", "agent-plugins:user"}:
            raise OmpInventoryError(
                "OMP skill inventory provider disagrees with package"
            )
        # Discovery names SKILL.md, not a directory. Validate its ancestry
        # separately and reject a symlink at the file itself.
        regular_chain(path.parent)
        if path.is_symlink() or not path.is_file():
            raise OmpInventoryError("OMP discovered skill is unavailable")
        seen.add(path)
        attributed.add(root)
        records.append(
            NativeComponentInspection(
                "skill",
                row["name"],
                "resolved"
                if package.enabled is True
                else "disabled"
                if package.enabled is False
                else "unobserved",
                "omp-skill-list",
                str(path),
            )
        )
    return records, attributed


def skill_components(stdout, packages):
    """Attribute native-discovered files only to independently inspected packages."""
    try:
        document = json.loads(stdout)
    except (TypeError, ValueError) as error:
        raise OmpInventoryError("OMP skill inventory is not valid JSON") from error
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("skills"), list)
        or not isinstance(document.get("warnings"), list)
    ):
        raise OmpInventoryError("OMP skill inventory is malformed")
    roots = {}
    for package in packages:
        if package.install_path is not None:
            root = Path(package.install_path)
            if root in roots:
                raise OmpInventoryError("OMP component package identity is ambiguous")
            roots[root] = package
    records, attributed = _attribute_skill_rows(document["skills"], roots)
    for root, package in roots.items():
        if root not in attributed:
            # Empty discovery does not prove that a package has no content.
            records.append(
                NativeComponentInspection(
                    "package-components",
                    package.package_name,
                    "unobserved",
                    "omp-skill-list",
                )
            )
    if any(
        not isinstance(row, dict) or not isinstance(row.get("message"), str)
        for row in document["warnings"]
    ):
        raise OmpInventoryError("OMP skill inventory warnings are malformed")
    errors = (
        ("OMP skill discovery reported warnings; coverage is unverified",)
        if document["warnings"]
        else ()
    )
    return tuple(records), errors
