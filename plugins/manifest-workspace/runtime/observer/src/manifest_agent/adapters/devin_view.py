"""Validation of generated generic plugin views consumed by Devin."""

import json
from collections.abc import Mapping

from manifest_agent.models import DesiredState


def _generic_view_errors(desired: DesiredState) -> list[str]:
    errors: list[str] = []
    for contract in desired.all_contracts:
        # The document `devin plugins install` reads. Checking the bundle-root
        # copy instead let the adapter pass while the native CLI rejected the
        # same directory for a missing manifest.
        path = desired.bundle_path(contract.name) / ".devin-plugin/plugin.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"{contract.name} has no readable plugin.json")
            continue
        if not isinstance(document, Mapping):
            errors.append(f"{contract.name} plugin.json is not an object")
            continue
        harnesses = document.get("harnesses")
        surface = harnesses.get("devin") if isinstance(harnesses, Mapping) else None
        expected_skills = _expected_skill_paths(desired, contract.name)
        compatibility = contract.compatibility.get("devin")
        expected_mode = compatibility.mode if compatibility is not None else None
        if (
            not expected_skills
            or document.get("name") != contract.name
            or document.get("version") != contract.version
            or document.get("skills") != list(expected_skills)
            or not isinstance(surface, Mapping)
            or surface.get("mode") != expected_mode
            or surface.get("skills") != list(expected_skills)
        ):
            errors.append(f"{contract.name} does not match its selected contract")
    return errors


def _expected_skill_paths(desired: DesiredState, bundle: str) -> tuple[str, ...]:
    contract = next(item for item in desired.all_contracts if item.name == bundle)
    bundle_root = desired.bundle_path(bundle)
    skills_root = bundle_root / contract.components.skills_root
    return tuple(
        sorted(
            {
                str(path.parent.relative_to(bundle_root))
                for pattern in contract.components.skills_include
                for path in skills_root.glob(pattern)
                if path.is_file()
            }
        )
    )
