"""Behavioral contracts for the OMP UI delivery lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from tools.generate_plugin_views import render_views


HARNESS_NAMES = (
    "claude",
    "codex",
    "gemini",
    "cursor",
    "antigravity",
    "devin",
)
TASK_STATES = {
    "draft",
    "approved",
    "building",
    "candidate_ready",
    "reviewing",
    "repairing",
    "accepted",
    "blocked",
    "failed",
}
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


def _schema(path: Path) -> Draft202012Validator:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def _assert_valid(validator: Draft202012Validator, instance: dict[str, Any]) -> None:
    assert not list(validator.iter_errors(instance))


def _assert_invalid(validator: Draft202012Validator, instance: dict[str, Any]) -> None:
    assert list(validator.iter_errors(instance))


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


def test_task_schema_enforces_authorized_bounded_lifecycle_semantics(
    repo_root: Path,
) -> None:
    validator = _schema(
        repo_root / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )
    task = {
        "task_id": "ui-delivery-17",
        "state": "accepted",
        "design_revision": "stitch-revision-71",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:8d5f2e",
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [
            {
                "id": "checkout-ui",
                "argv": ["npm", "run", "test:ui", "--", "CheckoutCard"],
                "cwd": "apps/web",
                "timeout_ms": 120000,
                "backend": "sandbox-exec",
                "env": ["CI"],
                "artifacts": [{"path": "artifacts/checkout-ui.xml", "type": "junit"}],
            }
        ],
        "capture_recipes": [
            {
                "id": "checkout-capture",
                "check_id": "checkout-ui",
                "artifacts": [{"path": "artifacts/checkout.png", "type": "image"}],
            }
        ],
        "model_route": "@ui_code",
        "repair_cycles": 2,
        "evidence_refs": ["artifact://ui-delivery-17/review.json"],
        "outcome": "verified",
    }

    _assert_valid(validator, task)

    for state in TASK_STATES:
        candidate = dict(task, state=state)
        if state == "accepted":
            candidate["outcome"] = "verified"
        elif state == "blocked":
            candidate["outcome"] = "blocked"
        elif state == "failed":
            candidate["outcome"] = "failed"
        else:
            candidate["outcome"] = "unverified"
        _assert_valid(validator, candidate)

    candidate_ready = {**task, "state": "candidate_ready", "outcome": "unverified"}
    _assert_valid(validator, candidate_ready)
    _assert_invalid(
        validator,
        {key: value for key, value in candidate_ready.items() if key != "candidate_revision"},
    )
    _assert_invalid(
        validator,
        {key: value for key, value in candidate_ready.items() if key != "candidate_hash"},
    )
    _assert_valid(
        validator,
        {
            **task,
            "stitch_grant": {
                "project_id": "stitch-project-17",
                "expires_at": "2030-01-01T00:00:00Z",
                "mutations": [
                    {
                        "tool_name": "stitch.edit_screen",
                        "input_hash": "sha256:8d5f2e",
                        "max_uses": 1,
                    }
                ],
                "readback_tools": ["stitch.get_screen"],
            },
        },
    )

    _assert_invalid(validator, {key: value for key, value in task.items() if key != "allowed_paths"})
    _assert_invalid(validator, {key: value for key, value in task.items() if key != "forbidden_policy_paths"})
    _assert_invalid(
        validator,
        {**task, "approved_check_recipes": ["npm run test:ui -- CheckoutCard"]},
    )
    _assert_invalid(validator, {key: value for key, value in task.items() if key != "capture_recipes"})
    _assert_invalid(validator, {key: value for key, value in task.items() if key != "evidence_refs"})
    _assert_invalid(validator, {**task, "repair_cycles": 3})
    _assert_invalid(validator, {**task, "state": "accepted", "outcome": "unverified"})
    _assert_invalid(validator, {**task, "state": "blocked", "outcome": "verified"})
    _assert_invalid(validator, {**task, "state": "cancelled"})
    _assert_invalid(validator, {**task, "outcome": "passed"})
    _assert_invalid(
        validator,
        {
            **task,
            "stitch_grant": {
                "project_id": "stitch-project-17",
                "expires_at": "2030-01-01T00:00:00Z",
                "mutations": [
                    {
                        "tool_name": "stitch.edit_screen",
                        "input_hash": "sha256:8d5f2e",
                        "max_uses": 2,
                    }
                ],
                "readback_tools": ["stitch.get_screen"],
            },
        },
    )
    _assert_invalid(validator, {**task, "unexpected": True})
    _assert_invalid(
        validator,
        {
            **task,
            "approved_check_recipes": [
                {**task["approved_check_recipes"][0], "shell": "npm test"}
            ],
        },
    )


def test_task_state_requirements_follow_lifecycle_boundaries(repo_root: Path) -> None:
    validator = _schema(
        repo_root / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )
    active = {
        "task_id": "ui-delivery-18",
        "state": "draft",
        "design_revision": "stitch-revision-72",
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [
            {
                "id": "checkout-ui",
                "argv": ["npm", "run", "test:ui"],
                "cwd": "apps/web",
                "timeout_ms": 1000,
                "backend": "docker",
            }
        ],
        "capture_recipes": [
            {
                "id": "checkout-capture",
                "check_id": "checkout-ui",
                "artifacts": [{"path": "artifacts/checkout.png", "type": "image"}],
            }
        ],
        "model_route": "@ui_code",
        "repair_cycles": 0,
        "outcome": "unverified",
    }

    _assert_valid(validator, active)
    _assert_valid(validator, {**active, "state": "approved"})
    candidate_ready = {
        **active,
        "state": "candidate_ready",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:8d5f2e",
    }
    _assert_valid(validator, candidate_ready)
    for state in ("reviewing", "repairing"):
        _assert_valid(validator, {**candidate_ready, "state": state})
    _assert_invalid(validator, {**active, "state": "candidate_ready"})
    for state, outcome in (("accepted", "verified"), ("failed", "failed"), ("blocked", "blocked")):
        terminal = {**candidate_ready, "state": state, "outcome": outcome}
        _assert_invalid(validator, terminal)
        _assert_valid(
            validator,
            {**terminal, "evidence_refs": ["artifact://ui-delivery-18/result.json"]},
        )


def test_review_schema_binds_read_only_verdict_to_exact_candidate_evidence(
    repo_root: Path,
) -> None:
    validator = _schema(
        repo_root
        / "plugins/stitch-design/skills/ui-verification/references/review.schema.json"
    )
    review = {
        "task_id": "ui-delivery-17",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:8d5f2e",
        "reviewer_model_route": "@ui_review",
        "verdict": "accepted",
        "repair_cycles": 2,
        "evidence_refs": ["artifact://ui-delivery-17/capture.png"],
        "outcome": "verified",
    }

    _assert_valid(validator, review)
    _assert_invalid(validator, {key: value for key, value in review.items() if key != "candidate_revision"})
    _assert_invalid(validator, {key: value for key, value in review.items() if key != "candidate_hash"})
    _assert_invalid(validator, {key: value for key, value in review.items() if key != "evidence_refs"})
    _assert_invalid(validator, {**review, "repair_cycles": 3})
    _assert_invalid(validator, {**review, "verdict": "accepted", "outcome": "unverified"})
    _assert_invalid(
        validator,
        {**review, "changed_paths": ["src/components/CheckoutCard.tsx"]},
    )


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
            assert status["mode"] in {"unsupported", "degraded"}, (agent_id, harness)
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
    assert {"./skills/ui-delivery", "./skills/ui-verification"} <= set(
        claude["skills"]
    )
    assert "./agents/ui-builder.md" not in claude.get("agents", [])
    assert "./agents/ui-reviewer.md" not in claude.get("agents", [])

    gemini = json.loads(
        (tmp_path / "stitch-design/gemini-extension.json").read_text(
            encoding="utf-8"
        )
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
    for unsupported in compatibility_surfaces:
        records = {
            record["component_id"]: record
            for record in unsupported
            if record["mode"] == "unsupported"
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
            (tmp_path / f"stitch-design/skills/{skill_name}/agents/openai.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert metadata == {"policy": {"allow_implicit_invocation": False}}
