"""T1.2 (spec 674) — the naming fork between Claude and the sibling harnesses.

Post-cutover a skill is reachable only as `<bundle>:<skill>`, but the two
audiences diverge permanently: docs/COMMANDS.md and /help must show what a
Claude Code user types, while the injected Gemini/Codex/Cursor index must keep
showing BARE names, because those harnesses read the sibling skills tree and
never learn about plugins. One string cannot serve both.

The default MUST stay bare/bare until bundles are installed: emitting
`/manifest-forge:git-commit` today documents a command that returns Unknown
command.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "configs" / "claude" / "scripts")
)
import generate_commands_doc as g


@pytest.fixture(autouse=True)
def _clear_era():
    os.environ.pop("SKILL_NAME_ERA", None)
    yield
    os.environ.pop("SKILL_NAME_ERA", None)


def test_default_era_is_bare_for_both_audiences():
    assert g.command_name("git-commit", "claude") == "/git-commit"
    assert g.command_name("git-commit", "sibling") == "/git-commit"


def test_qualified_era_only_changes_the_claude_audience():
    os.environ["SKILL_NAME_ERA"] = "qualified"
    assert g.command_name("git-commit", "claude") == "/manifest-forge:git-commit"
    assert g.command_name("git-commit", "sibling") == "/git-commit"


def test_siblings_never_get_a_bundle_prefix():
    """The whole point of the fork: siblings read the tree, not the plugins."""
    os.environ["SKILL_NAME_ERA"] = "qualified"
    for skill in ("upload-to-stitch", "ci-setup", "project-verify"):
        assert g.command_name(skill, "sibling") == f"/{skill}"


def test_unknown_skill_falls_back_to_bare_rather_than_emitting_a_broken_name():
    os.environ["SKILL_NAME_ERA"] = "qualified"
    assert g.command_name("not-a-real-skill", "claude") == "/not-a-real-skill"


def test_unreadable_registry_falls_back_to_bare(tmp_path: Path):
    os.environ["SKILL_NAME_ERA"] = "qualified"
    os.environ["MANIFEST_SKILL_REGISTRY"] = str(tmp_path / "nope.yml")
    try:
        assert g.command_name("git-commit", "claude") == "/git-commit"
    finally:
        os.environ.pop("MANIFEST_SKILL_REGISTRY", None)
