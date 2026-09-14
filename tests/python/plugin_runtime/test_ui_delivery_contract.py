"""Behavioral contracts for the OMP UI delivery lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.generate_plugin_views import render_views

HARNESS_NAMES = (
    "claude",
    "codex",
    "gemini",
    "cursor",
    "antigravity",
    "devin",
)
BUILDER_TOOLS = ["read", "grep", "glob", "ui_apply_patch", "ui_run_check"]
REVIEWER_TOOLS = ["read", "grep", "glob", "ui_capture"]


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _frontmatter(path: Path) -> dict[str, Any]:
    _, frontmatter, _ = path.read_text(encoding="utf-8").split("---", 2)
    document = yaml.safe_load(frontmatter)
    assert isinstance(document, dict)
    return document


def test_lifecycle_skills_are_portable_agent_skills_with_namespaced_handoffs(
    repo_root: Path,
) -> None:
    delivery = repo_root / "plugins/stitch-design/skills/ui-delivery/SKILL.md"
    verification = repo_root / "plugins/stitch-design/skills/ui-verification/SKILL.md"

    for skill_path, name in (
        (delivery, "ui-delivery"),
        (verification, "ui-verification"),
    ):
        metadata = _frontmatter(skill_path)
        assert set(metadata) == {"name", "description"}
        assert metadata["name"] == name
        assert isinstance(metadata["description"], str)
        assert 0 < len(metadata["description"]) <= 200
    assert "/stitch-design:ui-verification" in delivery.read_text(encoding="utf-8")
    assert "/stitch-design:ui-delivery" in verification.read_text(encoding="utf-8")


def test_delivery_preflight_requires_omp_assets_without_unrestricted_fallback(
    repo_root: Path,
) -> None:
    delivery = (
        repo_root / "plugins/stitch-design/skills/ui-delivery/SKILL.md"
    ).read_text(encoding="utf-8")

    for required_asset in (
        "ui-delivery",
        "ui-verification",
        "ui-builder",
        "ui-reviewer",
        "ui_apply_patch",
        "ui_run_check",
        "ui_capture",
        "task.schema.json",
        "review.schema.json",
    ):
        assert required_asset in delivery
    assert "unrestricted fallback" in delivery.lower()
    assert "blocks work" in delivery.lower()


def test_a11y_reports_evidence_categories_without_conformance_claims(
    repo_root: Path,
) -> None:
    source = (repo_root / "plugins/stitch-design/skills/a11y-audit/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "AA Conformant" not in source
    assert "| Principle | Checks | Pass | Fail | N/A |" not in source
    for category in (
        "verified automated checks",
        "failures",
        "manual-required",
        "skipped",
        "unavailable",
    ):
        assert category in source.lower()


def test_design_generation_removes_unbounded_variant_and_curl_guidance(
    repo_root: Path,
) -> None:
    source = (
        (repo_root / "plugins/stitch-design/skills/generate-design/SKILL.md")
        .read_text(encoding="utf-8")
        .lower()
    )

    assert "curl -o" not in source
    assert '"variantcount": 3' not in source
    assert "default: 3" not in source
    assert "no more than two candidates" in source


def test_omp_agents_are_constrained_to_their_declared_roles(repo_root: Path) -> None:
    builder = _frontmatter(repo_root / "plugins/stitch-design/agents/ui-builder.md")
    reviewer = _frontmatter(repo_root / "plugins/stitch-design/agents/ui-reviewer.md")

    assert builder["model"] == "@ui_code"
    assert builder["tools"] == BUILDER_TOOLS
    assert reviewer["model"] == "@ui_review"
    assert reviewer["tools"] == REVIEWER_TOOLS


def test_omp_only_agents_have_explicit_non_native_harness_compatibility(
    repo_root: Path,
) -> None:
    contract = yaml.safe_load(
        (repo_root / "plugins/stitch-design/manifest-capabilities.yml").read_text(
            encoding="utf-8"
        )
    )
    agents = {agent["id"]: agent for agent in contract["components"]["agents"]}

    for agent_id in ("ui-builder", "ui-reviewer"):
        compatibility = agents[agent_id]["compatibility"]
        assert set(compatibility) == set(HARNESS_NAMES)
        for harness, status in compatibility.items():
            assert status["mode"] == "not_applicable", (agent_id, harness)
            assert status["reason"].strip(), (agent_id, harness)


def test_portable_views_expose_skills_but_never_omp_only_agents(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)

    claude = json.loads(
        (tmp_path / "stitch-design/.claude-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert {"./skills/ui-delivery", "./skills/ui-verification"} <= set(claude["skills"])
    assert "./agents/ui-builder.md" not in claude.get("agents", [])
    assert "./agents/ui-reviewer.md" not in claude.get("agents", [])

    gemini = json.loads(
        (tmp_path / "stitch-design/gemini-extension.json").read_text(encoding="utf-8")
    )
    portable = json.loads(
        (tmp_path / "stitch-design/plugin.json").read_text(encoding="utf-8")
    )
    compatibility_surfaces = (
        claude["metadata"]["compatibility"]["degraded"],
        gemini["compatibility"]["degraded"],
        *(
            portable["harnesses"][harness]["compatibility"]["degraded"]
            for harness in ("antigravity", "codex", "cursor", "devin")
        ),
    )
    for records_for_harness in compatibility_surfaces:
        records = {
            record["component_id"]: record
            for record in records_for_harness
            if record["mode"] == "not_applicable"
        }
        assert records["ui-builder"]["path"] == "agents/ui-builder.md"
        assert records["ui-reviewer"]["path"] == "agents/ui-reviewer.md"

    for harness in ("antigravity", "codex", "cursor", "devin"):
        native_agents = portable["harnesses"][harness]["components"]["agents"]
        assert {agent["id"] for agent in native_agents}.isdisjoint(
            {"ui-builder", "ui-reviewer"}
        )

    for skill_name in ("ui-delivery", "ui-verification"):
        metadata = yaml.safe_load(
            (
                tmp_path / f"stitch-design/skills/{skill_name}/agents/openai.yaml"
            ).read_text(encoding="utf-8")
        )
        assert metadata == {"policy": {"allow_implicit_invocation": False}}
