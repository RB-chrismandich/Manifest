"""Every hardcoded domain-bundle inventory must match the canonical set.

Spec: `docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md`
section 9a -- "Add a CI assertion that every hardcoded inventory and workflow
trigger matches the canonical domain set, so this list cannot drift again."

Five inventories are genuinely hardcoded. Three are YAML/JSON/workflow files
where importing `DOMAIN_BUNDLES` is not an option, which is exactly why they
need an assertion rather than a refactor; the Python-side consumers already
import the constant and cannot drift.

Each inventory is parsed **structurally** rather than grepped for bundle names.
A grep-based gate misfires on files that mention a bundle for some other reason
-- `test_bundle_link_references_real_repo.py` names `manifest-delegate` inside a
single true-positive assertion and omits two domain bundles no assertion needed,
which reads as drift and is not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from manifest_agent.contracts import ADDON_BUNDLES, DOMAIN_BUNDLES

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = set(DOMAIN_BUNDLES)


def _load_yaml(relative: str) -> dict:
    return yaml.safe_load((REPO_ROOT / relative).read_text(encoding="utf-8"))


def test_skill_policies_bundles_cover_every_domain_bundle() -> None:
    """`skill_policies.yml` also carries addons and marketplace-only bundles,
    so containment is the correct relation here, not equality."""
    partitions = set(_load_yaml("configs/claude/config/skill_policies.yml")["bundles"])

    assert partitions >= CANONICAL, (
        f"domain bundles missing from skill_policies.yml bundles: "
        f"{sorted(CANONICAL - partitions)}"
    )
    for extra in sorted(partitions - CANONICAL - set(ADDON_BUNDLES)):
        assert (REPO_ROOT / "plugins" / extra).is_dir(), (
            f"skill_policies.yml bundles names {extra!r}, which is neither a "
            f"domain bundle, an addon, nor a directory under plugins/"
        )


def test_marketplace_manifest_offers_every_domain_bundle() -> None:
    manifest = json.loads(
        (REPO_ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    offered = {entry["name"] for entry in manifest["plugins"]}

    assert offered >= CANONICAL, (
        f"marketplace.json does not offer: {sorted(CANONICAL - offered)}"
    )


def test_release_workflow_triggers_on_exactly_the_domain_bundles() -> None:
    """A release must fire for every domain bundle and no other plugin: a
    missing trigger silently stops publishing a bundle, and an extra one
    publishes a release for a bundle the archive does not contain."""
    # `on` parses as the YAML boolean True, not the string "on".
    workflow = _load_yaml(".github/workflows/manifest-release.yml")
    paths = workflow[True]["push"]["paths"]
    triggered = {
        match.group(1)
        for match in (re.fullmatch(r"plugins/([^/]+)/\*\*", p) for p in paths)
        if match
    }

    assert triggered == CANONICAL, (
        f"release trigger drift -- missing {sorted(CANONICAL - triggered)}, "
        f"unexpected {sorted(triggered - CANONICAL)}"
    )


def test_parity_workflow_inlines_exactly_the_domain_bundles() -> None:
    """The parity job embeds its own DOMAIN_BUNDLES tuple in an inline script,
    so it cannot import the constant and is the likeliest to drift."""
    text = (REPO_ROOT / ".github/workflows/plugin-parity-live.yml").read_text(
        encoding="utf-8"
    )
    block = re.search(r"DOMAIN_BUNDLES = \((.*?)\)", text, re.S)
    assert block is not None, "plugin-parity-live.yml no longer inlines DOMAIN_BUNDLES"
    inlined = set(re.findall(r'"([^"]+)"', block.group(1)))

    assert inlined == CANONICAL, (
        f"parity workflow drift -- missing {sorted(CANONICAL - inlined)}, "
        f"unexpected {sorted(inlined - CANONICAL)}"
    )


def test_capability_tier_fixture_covers_exactly_the_domain_bundles() -> None:
    fixture = json.loads(
        (REPO_ROOT / "tests/python/fixtures/expected_capability_tiers.json").read_text(
            encoding="utf-8"
        )
    )
    covered = set(fixture)

    assert covered == CANONICAL, (
        f"capability-tier fixture drift -- missing {sorted(CANONICAL - covered)}, "
        f"unexpected {sorted(covered - CANONICAL)}"
    )


@pytest.mark.parametrize("bundle", sorted(DOMAIN_BUNDLES))
def test_every_canonical_bundle_has_a_directory(bundle: str) -> None:
    """Anchors the other five: without this they would all agree with each
    other about a bundle that does not exist."""
    assert (REPO_ROOT / "plugins" / bundle).is_dir()
