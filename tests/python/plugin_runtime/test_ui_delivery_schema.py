"""Schema-level contracts for the OMP UI delivery lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.python.plugin_runtime.ui_delivery_contract_support import (
    assert_invalid,
    assert_no_response_format_conditionals,
    assert_valid,
    capture_recipe,
    docker_check_recipe,
    frontmatter,
    schema,
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

QUALIFICATION_HASH = (
    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _accepted_task() -> dict[str, Any]:
    return {
        "task_id": "ui-delivery-17",
        "state": "accepted",
        "design_revision": "stitch-revision-71",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "qualification_hash": QUALIFICATION_HASH,
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [
            {
                **docker_check_recipe(),
                "argv": ["node", ".omp/ui-delivery/verifiers/check-ui.mjs"],
                "timeout_ms": 120000,
                "backend": "docker",
                "artifacts": [{"path": "artifacts/checkout-ui.xml", "type": "junit"}],
            }
        ],
        "capture_recipes": [capture_recipe()],
        "model_route": "@ui_review",
        "repair_cycles": 2,
        "evidence_refs": ["artifact://ui-delivery-17/review.json"],
        "outcome": "verified",
    }


def _with_check_recipe(task: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    recipe = task["approved_check_recipes"][0]
    return {**task, "approved_check_recipes": [{**recipe, **overrides}]}


def _validator(repo_root: Path) -> Draft202012Validator:
    return schema(
        repo_root
        / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )


def test_task_schema_accepts_authorized_lifecycle_states(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()

    assert_valid(validator, task)
    assert_invalid(validator, {**task, "model_route": "@ui_code"})
    for state in TASK_STATES:
        outcome = "verified" if state == "accepted" else "unverified"
        if state in {"blocked", "failed"}:
            outcome = state
        lifecycle_task = {**task, "state": state, "outcome": outcome}
        if state == "repairing":
            lifecycle_task["repair_authorization"] = {
                "cycle": task["repair_cycles"],
                "nonce": "repair-cycle-2",
            }
        assert_valid(validator, lifecycle_task)


def test_task_schema_forbids_repair_authorization_outside_repairing_state(
    repo_root: Path,
) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()

    assert_invalid(
        validator,
        {**task, "state": "accepted", "repair_authorization": {"cycle": 2, "nonce": "stale-repair"}},
    )
    assert_invalid(
        validator,
        {**task, "state": "building", "outcome": "unverified", "repair_authorization": {"cycle": 1, "nonce": "premature"}},
    )


def test_task_schema_requires_candidate_identity_and_allows_review_route(
    repo_root: Path,
) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()
    candidate = {**task, "state": "candidate_ready", "outcome": "unverified"}

    assert_valid(validator, candidate)
    for state in ("candidate_ready", "reviewing"):
        assert_valid(
            validator, {**candidate, "state": state, "model_route": "@ui_review"}
        )
    assert_invalid(validator, {**candidate, "model_route": "@unknown_route"})
    assert_invalid(
        validator,
        {key: value for key, value in candidate.items() if key != "candidate_revision"},
    )
    assert_invalid(
        validator,
        {key: value for key, value in candidate.items() if key != "candidate_hash"},
    )
    assert_invalid(validator, {**candidate, "candidate_hash": "sha256:8d5f2e"})


def test_task_schema_enforces_required_fields_and_outcomes(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()

    for field in (
        "allowed_paths",
        "forbidden_policy_paths",
        "capture_recipes",
        "qualification_hash",
        "evidence_refs",
    ):
        assert_invalid(
            validator, {key: value for key, value in task.items() if key != field}
        )
    assert_invalid(
        validator,
        {**task, "approved_check_recipes": ["npm run test:ui -- CheckoutCard"]},
    )
    assert_invalid(validator, _with_check_recipe(task, env=["CI"]))
    assert_invalid(validator, {**task, "state": "accepted", "outcome": "unverified"})
    assert_invalid(validator, {**task, "state": "blocked", "outcome": "verified"})
    assert_invalid(validator, {**task, "state": "cancelled"})
    assert_invalid(validator, {**task, "outcome": "passed"})
    assert_invalid(validator, {**task, "unexpected": True})
    assert_invalid(validator, {**task, "qualification_hash": "sha256:" + "B" * 64})


def test_task_schema_rejects_unsafe_ids_and_whitespace_paths(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()

    assert_invalid(validator, {**task, "task_id": "../ui-delivery-17"})
    assert_invalid(validator, {**task, "allowed_paths": ["."]})
    assert_invalid(validator, {**task, "allowed_paths": ["src/Checkout Card.tsx"]})
    for noncanonical in ("./src/CheckoutCard.tsx", "src//CheckoutCard.tsx"):
        assert_invalid(validator, {**task, "allowed_paths": [noncanonical]})
    assert_invalid(
        validator,
        _with_check_recipe(task, write_paths=["artifacts/check result.json"]),
    )
    assert_invalid(
        validator,
        _with_check_recipe(task, result_path=".", write_paths=["."]),
    )
    assert_invalid(
        validator,
        _with_check_recipe(
            task,
            write_paths=[task["approved_check_recipes"][0]["result_path"], "."],
        ),
    )
    assert_invalid(
        validator,
        {
            **task,
            "capture_recipes": [
                {
                    **task["capture_recipes"][0],
                    "artifacts": [
                        {"path": "artifacts/checkout capture.png", "type": "image"}
                    ],
                }
            ],
        },
    )


def test_task_schema_requires_complete_hardened_check_recipes(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()
    recipe = task["approved_check_recipes"][0]

    for field in ("write_paths", "result_path"):
        incomplete = {key: value for key, value in recipe.items() if key != field}
        assert_invalid(validator, {**task, "approved_check_recipes": [incomplete]})
    assert_invalid(validator, _with_check_recipe(task, shell="npm test"))
    assert_invalid(
        validator,
        _with_check_recipe(task, sandbox_image="registry.example/ui-check:latest"),
    )
    assert_invalid(
        validator,
        _with_check_recipe(
            task,
            backend="docker",
            sandbox_image="registry.example/ui-check@sha512:0123456789abcdef",
        ),
    )
    assert_valid(
        validator,
        _with_check_recipe(
            task,
            backend="docker",
            argv=["node", ".omp/ui-delivery/verifiers/check-ui.mjs"],
            sandbox_image="registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ),
    )
    assert_invalid(
        validator,
        _with_check_recipe(
            task,
            backend="docker",
            argv=[".omp/ui-delivery/verifiers/check-ui.mjs"],
        ),
    )
    incomplete = {key: value for key, value in recipe.items() if key != "sandbox_image"}
    assert_invalid(
        validator,
        {**task, "approved_check_recipes": [incomplete | {"backend": "docker"}]},
    )


def test_task_schema_requires_evidence_for_terminal_candidate_states(
    repo_root: Path,
) -> None:
    validator = _validator(repo_root)
    active = {
        "task_id": "ui-delivery-18",
        "state": "draft",
        "design_revision": "stitch-revision-72",
        "qualification_hash": QUALIFICATION_HASH,
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [docker_check_recipe()],
        "capture_recipes": [capture_recipe()],
        "model_route": "@ui_code",
        "repair_cycles": 0,
        "outcome": "unverified",
    }

    assert_valid(validator, active)
    assert_valid(validator, {**active, "state": "approved"})
    candidate = {
        **active,
        "state": "candidate_ready",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }
    assert_valid(validator, candidate)
    assert_valid(validator, {**candidate, "state": "reviewing"})
    assert_valid(
        validator,
        {
            **candidate,
            "state": "repairing",
            "repair_cycles": 1,
            "repair_authorization": {"cycle": 1, "nonce": "repair-cycle-1"},
        },
    )
    assert_invalid(validator, {**active, "state": "candidate_ready"})
    for state, outcome in (
        ("accepted", "verified"),
        ("failed", "failed"),
        ("blocked", "blocked"),
    ):
        terminal = {
            **candidate,
            "state": state,
            "outcome": outcome,
            **({"model_route": "@ui_review"} if state == "accepted" else {}),
        }
        assert_invalid(validator, terminal)
        assert_valid(
            validator,
            {**terminal, "evidence_refs": ["artifact://ui-delivery-18/result.json"]},
        )


def test_task_schema_allows_pre_candidate_failures_with_evidence(
    repo_root: Path,
) -> None:
    validator = _validator(repo_root)
    terminal = {
        "task_id": "ui-delivery-19",
        "design_revision": "stitch-revision-73",
        "qualification_hash": QUALIFICATION_HASH,
        "allowed_paths": ["src/components/CheckoutCard.tsx"],
        "forbidden_policy_paths": [".claude/settings.json"],
        "approved_check_recipes": [docker_check_recipe()],
        "capture_recipes": [capture_recipe()],
        "model_route": "@ui_code",
        "repair_cycles": 0,
        "evidence_refs": ["artifact://ui-delivery-19/error.json"],
    }

    assert_valid(validator, {**terminal, "state": "blocked", "outcome": "blocked"})
    assert_valid(validator, {**terminal, "state": "failed", "outcome": "failed"})


def test_agent_output_schemas_are_strict_and_match_the_review_contract(
    repo_root: Path,
) -> None:
    review_schema = json.loads(
        (
            repo_root
            / "plugins/stitch-design/skills/ui-verification/references/review.schema.json"
        ).read_text(encoding="utf-8")
    )
    reviewer_output = frontmatter(
        repo_root / "plugins/stitch-design/agents/ui-reviewer.md"
    )["output"]
    for document in (review_schema, reviewer_output):
        assert document["additionalProperties"] is False
        assert set(document["required"]) == set(document["properties"])
        assert_no_response_format_conditionals(document)
    assert set(reviewer_output["properties"]) == set(review_schema["properties"])
    assert set(reviewer_output["required"]) == set(review_schema["required"])
    assert reviewer_output["oneOf"] == review_schema["oneOf"]
    assert "outcome" not in reviewer_output["properties"]
    assert "outcome" not in review_schema["properties"]
    for field in ("findings", "reviewer_model_route", "verdict", "repair_cycles"):
        assert field in reviewer_output["properties"]
        assert field in reviewer_output["required"]

    for agent_name in ("ui-builder", "ui-reviewer"):
        output = frontmatter(
            repo_root / f"plugins/stitch-design/agents/{agent_name}.md"
        )["output"]
        assert output["additionalProperties"] is False
        assert set(output["required"]) == set(output["properties"])
        assert_no_response_format_conditionals(output)
        for field in ("task_id", "candidate_revision", "candidate_hash"):
            assert output["properties"][field]["minLength"] == 1
        assert output["properties"]["evidence_refs"]["minItems"] == 1


def test_review_schema_binds_read_only_verdict_to_exact_candidate_evidence(
    repo_root: Path,
) -> None:
    validator = schema(
        repo_root
        / "plugins/stitch-design/skills/ui-verification/references/review.schema.json"
    )
    review = {
        "task_id": "ui-delivery-17",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:8d5f2e",
        "reviewer_model_route": "@ui_review",
        "verdict": "accepted",
        "findings": [],
        "repair_cycles": 2,
        "evidence_refs": ["artifact://ui-delivery-17/capture.png"],
    }

    assert_valid(validator, review)
    assert_invalid(validator, {**review, "findings": ["Incorrect spacing."]})
    review_at_cycle_1 = {**review, "repair_cycles": 1}
    assert_valid(
        validator,
        {**review_at_cycle_1, "verdict": "repair_required", "findings": ["Incorrect spacing."]},
    )
    assert_invalid(
        validator,
        {**review_at_cycle_1, "verdict": "repair_required", "findings": []},
    )
    assert_invalid(
        validator,
        {**review, "verdict": "repair_required", "findings": ["Incorrect spacing."]},
    )
    assert_invalid(
        validator,
        {**review, "verdict": "blocked", "findings": []},
    )
    assert_invalid(
        validator,
        {**review, "verdict": "failed", "findings": []},
    )
    assert_valid(
        validator,
        {**review, "verdict": "blocked", "findings": ["Incorrect spacing."]},
    )
    assert_invalid(
        validator,
        {key: value for key, value in review.items() if key != "candidate_revision"},
    )
    assert_invalid(
        validator,
        {key: value for key, value in review.items() if key != "candidate_hash"},
    )
    assert_invalid(
        validator,
        {key: value for key, value in review.items() if key != "evidence_refs"},
    )
    assert_invalid(validator, {**review, "repair_cycles": 3})
    assert_invalid(validator, {**review, "outcome": "verified"})
    assert_invalid(
        validator,
        {**review, "changed_paths": ["src/components/CheckoutCard.tsx"]},
    )
