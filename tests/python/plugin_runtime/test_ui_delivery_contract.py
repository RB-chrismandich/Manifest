"""Behavioral contracts for the OMP UI delivery lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

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
    return Draft202012Validator(document, format_checker=FormatChecker())


def _assert_valid(validator: Draft202012Validator, instance: dict[str, Any]) -> None:
    assert not list(validator.iter_errors(instance))


def _assert_invalid(validator: Draft202012Validator, instance: dict[str, Any]) -> None:
    assert list(validator.iter_errors(instance))


def _with_check_recipe(task: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    recipe = task["approved_check_recipes"][0]
    return {**task, "approved_check_recipes": [{**recipe, **overrides}]}


def _docker_check_recipe() -> dict[str, Any]:
    return {
        "id": "checkout-ui",
        "argv": ["npm", "run", "test:ui"],
        "cwd": "apps/web",
        "write_paths": [
            "artifacts/checkout-ui.result.json",
            "artifacts/checkout.png",
        ],
        "timeout_ms": 1000,
        "backend": "docker",
        "sandbox_image": "registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "result_path": "artifacts/checkout-ui.result.json",
    }


def _capture_recipe() -> dict[str, Any]:
    return {
        "id": "checkout-capture",
        "check_id": "checkout-ui",
        "artifacts": [{"path": "artifacts/checkout.png", "type": "image"}],
    }


def _assert_no_response_format_conditionals(schema: Any) -> None:
    if isinstance(schema, dict):
        assert not {"allOf", "if", "then"} & schema.keys()
        properties = schema.get("properties")
        if properties is not None:
            assert isinstance(properties, dict)
            for property_name, property_schema in properties.items():
                assert isinstance(property_schema, dict), property_name
                assert "type" in property_schema, property_name
        for value in schema.values():
            _assert_no_response_format_conditionals(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_no_response_format_conditionals(value)


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
        repo_root
        / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )
    task = {
        "task_id": "ui-delivery-17",
        "state": "accepted",
        "design_revision": "stitch-revision-71",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [
            {
                "id": "checkout-ui",
                "argv": ["npm", "run", "test:ui", "--", "CheckoutCard"],
                "cwd": "apps/web",
                "timeout_ms": 120000,
                "backend": "sandbox-exec",
                "sandbox_image": "registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "result_path": "artifacts/checkout-ui.result.json",
                "write_paths": [
                    "artifacts/checkout-ui.result.json",
                    "artifacts/checkout.png",
                ],
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

    stitch_grant = {
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
    }

    candidate_ready = {**task, "state": "candidate_ready", "outcome": "unverified"}
    _assert_valid(validator, candidate_ready)
    _assert_invalid(
        validator,
        {**task, "stitch_grant": {**stitch_grant, "expires_at": "not-a-date"}},
    )

    for state in ("candidate_ready", "reviewing"):
        _assert_valid(
            validator,
            {**candidate_ready, "state": state, "model_route": "@ui_review"},
        )
    _assert_invalid(
        validator,
        {**candidate_ready, "model_route": "@unknown_route"},
    )
    _assert_invalid(
        validator,
        {
            key: value
            for key, value in candidate_ready.items()
            if key != "candidate_revision"
        },
    )
    _assert_invalid(
        validator,
        {
            key: value
            for key, value in candidate_ready.items()
            if key != "candidate_hash"
        },
    )
    _assert_invalid(
        validator,
        {**candidate_ready, "candidate_hash": "sha256:8d5f2e"},
    )
    _assert_valid(
        validator,
        {
            **task,
            "stitch_grant": stitch_grant,
        },
    )

    _assert_invalid(
        validator, {key: value for key, value in task.items() if key != "allowed_paths"}
    )
    _assert_invalid(
        validator,
        {key: value for key, value in task.items() if key != "forbidden_policy_paths"},
    )
    _assert_invalid(
        validator,
        {**task, "approved_check_recipes": ["npm run test:ui -- CheckoutCard"]},
    )
    _assert_invalid(
        validator,
        {
            **task,
            "approved_check_recipes": [
                {
                    key: value
                    for key, value in task["approved_check_recipes"][0].items()
                    if key != "write_paths"
                }
            ],
        },
    )
    _assert_invalid(
        validator,
        {key: value for key, value in task.items() if key != "capture_recipes"},
    )
    _assert_invalid(
        validator, {key: value for key, value in task.items() if key != "evidence_refs"}
    )
    _assert_invalid(validator, _with_check_recipe(task, env=["CI"]))
    _assert_invalid(
        validator,
        {
            **task,
            "approved_check_recipes": [
                {
                    key: value
                    for key, value in task["approved_check_recipes"][0].items()
                    if key != "result_path"
                }
            ],
        },
    )
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
    _assert_invalid(validator, _with_check_recipe(task, shell="npm test"))

    _assert_invalid(
        validator,
        _with_check_recipe(task, sandbox_image="registry.example/ui-check:latest"),
    )

    _assert_invalid(
        validator,
        _with_check_recipe(
            task,
            backend="docker",
            sandbox_image="registry.example/ui-check@sha512:0123456789abcdef",
        ),
    )

    _assert_valid(
        validator,
        _with_check_recipe(
            task,
            backend="docker",
            sandbox_image="registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ),
    )
    _assert_invalid(
        validator,
        {
            **task,
            "approved_check_recipes": [
                {
                    key: value
                    for key, value in task["approved_check_recipes"][0].items()
                    if key != "sandbox_image"
                }
                | {"backend": "docker"}
            ],
        },
    )


def test_task_state_requirements_follow_lifecycle_boundaries(repo_root: Path) -> None:
    validator = _schema(
        repo_root
        / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )
    active = {
        "task_id": "ui-delivery-18",
        "state": "draft",
        "design_revision": "stitch-revision-72",
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [_docker_check_recipe()],
        "capture_recipes": [_capture_recipe()],
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
        "candidate_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }
    _assert_valid(validator, candidate_ready)
    for state in ("reviewing", "repairing"):
        _assert_valid(validator, {**candidate_ready, "state": state})
    _assert_invalid(validator, {**active, "state": "candidate_ready"})
    for state, outcome in (
        ("accepted", "verified"),
        ("failed", "failed"),
        ("blocked", "blocked"),
    ):
        terminal = {**candidate_ready, "state": state, "outcome": outcome}
        _assert_invalid(validator, terminal)
        _assert_valid(
            validator,
            {**terminal, "evidence_refs": ["artifact://ui-delivery-18/result.json"]},
        )


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


def test_blocked_and_failed_tasks_can_terminate_before_a_candidate_exists(
    repo_root: Path,
) -> None:
    validator = _schema(
        repo_root
        / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )
    terminal = {
        "task_id": "ui-delivery-19",
        "design_revision": "stitch-revision-73",
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [_docker_check_recipe()],
        "capture_recipes": [_capture_recipe()],
        "model_route": "@ui_code",
        "repair_cycles": 0,
        "evidence_refs": ["artifact://ui-delivery-19/error.json"],
    }

    _assert_valid(validator, {**terminal, "state": "blocked", "outcome": "blocked"})
    _assert_valid(validator, {**terminal, "state": "failed", "outcome": "failed"})


def test_agent_output_schemas_are_strict_and_match_the_review_contract(
    repo_root: Path,
) -> None:
    review_schema = json.loads(
        (
            repo_root
            / "plugins/stitch-design/skills/ui-verification/references/review.schema.json"
        ).read_text(encoding="utf-8")
    )
    reviewer_output = _frontmatter(
        repo_root / "plugins/stitch-design/agents/ui-reviewer.md"
    )["output"]
    for schema in (review_schema, reviewer_output):
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        _assert_no_response_format_conditionals(schema)
    assert set(reviewer_output["properties"]) == set(review_schema["properties"])
    assert set(reviewer_output["required"]) == set(review_schema["required"])
    assert "outcome" not in reviewer_output["properties"]
    assert "outcome" not in review_schema["properties"]
    for field in ("findings", "reviewer_model_route", "verdict", "repair_cycles"):
        assert field in reviewer_output["properties"]
        assert field in reviewer_output["required"]

    for agent_name in ("ui-builder", "ui-reviewer"):
        output = _frontmatter(
            repo_root / f"plugins/stitch-design/agents/{agent_name}.md"
        )["output"]
        assert output["additionalProperties"] is False
        assert set(output["required"]) == set(output["properties"])
        _assert_no_response_format_conditionals(output)
        for field in ("task_id", "candidate_revision", "candidate_hash"):
            assert output["properties"][field]["minLength"] == 1
        assert output["properties"]["evidence_refs"]["minItems"] == 1


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
        "findings": ["No blocking findings."],
        "repair_cycles": 2,
        "evidence_refs": ["artifact://ui-delivery-17/capture.png"],
    }

    _assert_valid(validator, review)
    _assert_invalid(
        validator,
        {key: value for key, value in review.items() if key != "candidate_revision"},
    )
    _assert_invalid(
        validator,
        {key: value for key, value in review.items() if key != "candidate_hash"},
    )
    _assert_invalid(
        validator,
        {key: value for key, value in review.items() if key != "evidence_refs"},
    )
    _assert_invalid(validator, {**review, "repair_cycles": 3})
    _assert_invalid(validator, {**review, "outcome": "verified"})
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
