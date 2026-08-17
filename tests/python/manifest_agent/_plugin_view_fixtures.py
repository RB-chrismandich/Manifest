"""Shared filesystem fixtures for plugin-view generation tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from manifest_agent.contracts import DOMAIN_BUNDLES


def build_fixture_repo(repo_root: Path, fixture_root: Path) -> None:
    """Copy the minimum canonical contract tree needed by generator tests."""
    fixture_plugins = fixture_root / "plugins"
    for bundle_name in DOMAIN_BUNDLES:
        source_bundle = repo_root / "plugins" / bundle_name
        target_bundle = fixture_plugins / bundle_name
        (target_bundle / "skills/example").mkdir(parents=True)
        shutil.copy2(
            source_bundle / "manifest-capabilities.yml",
            target_bundle / "manifest-capabilities.yml",
        )
        contract_document = yaml.safe_load(
            (source_bundle / "manifest-capabilities.yml").read_text(encoding="utf-8")
        )
        for component_type in ("agents", "hooks", "runtime", "guidance"):
            for component in contract_document["components"][component_type]:
                source = source_bundle / component["path"]
                target = target_bundle / component["path"]
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("fixture\n", encoding="utf-8")
        (target_bundle / "skills/example/SKILL.md").write_text(
            "---\nname: example\ndescription: Example fixture skill.\n---\n",
            encoding="utf-8",
        )

    marketplace_path = fixture_root / ".claude-plugin/marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    shutil.copy2(repo_root / ".claude-plugin/marketplace.json", marketplace_path)
    for source in sorted(
        (repo_root / "plugins").glob("*/.claude-plugin/marketplace-entry.json")
    ):
        target = fixture_plugins / source.relative_to(repo_root / "plugins")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    policy_path = fixture_root / "configs/claude/config/skill_policies.yml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        "codex_implicit_invocation_allowlist: []\n", encoding="utf-8"
    )
