"""Build the offline command catalog shipped with the workspace plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class CommandCatalogError(ValueError):
    """Raised when a skill cannot be represented in the command catalog."""


def _skill_frontmatter(skill_file: Path) -> dict[str, Any]:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise CommandCatalogError(f"{skill_file}: missing YAML frontmatter")
    try:
        _opening, frontmatter, _body = text.split("---", 2)
        document = yaml.safe_load(frontmatter)
    except (ValueError, yaml.YAMLError) as error:
        raise CommandCatalogError(
            f"{skill_file}: invalid frontmatter: {error}"
        ) from error
    if not isinstance(document, dict):
        raise CommandCatalogError(f"{skill_file}: frontmatter must be a mapping")
    return document


def build_command_catalog(
    source_plugins: Path, contracts: tuple[Any, ...]
) -> dict[str, Any]:
    """Return sorted command metadata derived from contracts and skill frontmatter."""
    commands: list[dict[str, str]] = []
    for contract in contracts:
        skills_root = source_plugins / contract.name / contract.components.skills_root
        for skill_file in sorted(skills_root.glob("*/SKILL.md")):
            skill_name = skill_file.parent.name
            frontmatter = _skill_frontmatter(skill_file)
            declared_name = frontmatter.get("name")
            description = frontmatter.get("description")
            if declared_name != skill_name:
                raise CommandCatalogError(
                    f"{skill_file}: frontmatter name {declared_name!r} "
                    f"must equal {skill_name!r}"
                )
            if not isinstance(description, str) or not description.strip():
                raise CommandCatalogError(
                    f"{skill_file}: description must be non-empty"
                )
            commands.append(
                {
                    "bundle": contract.name,
                    "category": contract.category,
                    "description": description.strip(),
                    "name": skill_name,
                    "qualified_name": f"{contract.name}:{skill_name}",
                }
            )
    return {
        "commands": sorted(
            commands, key=lambda item: (item["category"], item["qualified_name"])
        ),
        "schema_version": 1,
    }
