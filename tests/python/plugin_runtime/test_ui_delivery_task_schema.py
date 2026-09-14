"""Task and review schema contracts for the OMP UI delivery lifecycle."""

from __future__ import annotations

from pathlib import Path

from tests.python.plugin_runtime._ui_delivery_contract_harness import (
    TASK_STATES,
    accepted_task,
    assert_invalid,
    assert_valid,
    capture_recipe,
    docker_check_recipe,
    review_schema_path,
    schema,
    stitch_grant,
    task_schema_path,
    with_check_recipe,
)


def test_task_schema_accepts_valid_accepted_task(repo_root: Path) -> None:
    validator = schema(task_schema_path(repo_root))
    assert_valid(validator, accepted_task())


def test_task_schema_accepts_all_lifecycle_states(repo_root: Path) -> None:
    validator = schema(task_schema_path(repo_root))
    task = accepted_task()
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
        assert_valid(validator, candidate)


def test_task_schema_validates_stitch_grant_and_model_route(repo_root: Path) -> None:
    validator = schema(task_schema_path(repo_root))
    task = accepted_task()
    candidate_ready = {**task, "state": "candidate_ready", "outcome": "unverified"}
    assert_valid(validator, candidate_ready)
    assert_invalid(
        validator,
        {**task, "stitch_grant": {**stitch_grant(), "expires_at": "not-a-date"}},
    )
    for state in ("candidate_ready", "reviewing"):
        assert_valid(
            validator,
            {**candidate_ready, "state": state, "model_route": "@ui_review"},
        )
    assert_invalid(validator, {**candidate_ready, "model_route": "@unknown_route"})
    assert_invalid(
        validator,
        {
            key: value
            for key, value in candidate_ready.items()
            if key != "candidate_revision"
        },
    )
    assert_invalid(
        validator,
        {
            key: value
            for key, value in candidate_ready.items()
            if key != "candidate_hash"
        },
    )
    assert_invalid(validator, {**candidate_ready, "candidate_hash": "sha256:8d5f2e"})
    assert_valid(validator, {**task, "stitch_grant": stitch_grant()})


def test_task_schema_requires_core_fields(repo_root: Path) -> None:
    validator = schema(task_schema_path(repo_root))
    task = accepted_task()
    assert_invalid(
        validator, {key: value for key, value in task.items() if key != "allowed_paths"}
    )
    assert_invalid(
        validator,
        {key: value for key, value in task.items() if key != "forbidden_policy_paths"},
    )
    assert_invalid(
        validator,
        {**task, "approved_check_recipes": ["npm run test:ui -- CheckoutCard"]},
    )
    assert_invalid(
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
    assert_invalid(
        validator,
        {key: value for key, value in task.items() if key != "capture_recipes"},
    )
    assert_invalid(
        validator, {key: value for key, value in task.items() if key != "evidence_refs"}
    )


def test_task_schema_rejects_invalid_recipes_and_outcomes(repo_root: Path) -> None:
    validator = schema(task_schema_path(repo_root))
    task = accepted_task()
    assert_invalid(validator, with_check_recipe(task, env=["CI"]))
    assert_invalid(
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
    assert_invalid(validator, {**task, "state": "accepted", "outcome": "unverified"})
    assert_invalid(validator, {**task, "state": "blocked", "outcome": "verified"})
    assert_invalid(validator, {**task, "state": "cancelled"})
    assert_invalid(validator, {**task, "outcome": "passed"})
    assert_invalid(
        validator,
        {
            **task,
            "stitch_grant": {
                **stitch_grant(),
                "mutations": [{**stitch_grant()["mutations"][0], "max_uses": 2}],
            },
        },
    )
    assert_invalid(validator, {**task, "unexpected": True})
    assert_invalid(validator, with_check_recipe(task, shell="npm test"))


def test_task_schema_validates_sandbox_image_constraints(repo_root: Path) -> None:
    validator = schema(task_schema_path(repo_root))
    task = accepted_task()
    assert_invalid(
        validator,
        with_check_recipe(task, sandbox_image="registry.example/ui-check:latest"),
    )
    assert_invalid(
        validator,
        with_check_recipe(
            task,
            backend="docker",
            sandbox_image="registry.example/ui-check@sha512:0123456789abcdef",
        ),
    )
    assert_valid(
        validator,
        with_check_recipe(
            task,
            backend="docker",
            sandbox_image="registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ),
    )
    assert_invalid(
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
    validator = schema(task_schema_path(repo_root))
    active = {
        "task_id": "ui-delivery-18",
        "state": "draft",
        "design_revision": "stitch-revision-72",
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
    candidate_ready = {
        **active,
        "state": "candidate_ready",
        "candidate_revision": "git:4d2ce0b",
        "candidate_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }
    assert_valid(validator, candidate_ready)
    for state in ("reviewing", "repairing"):
        assert_valid(validator, {**candidate_ready, "state": state})
    assert_invalid(validator, {**active, "state": "candidate_ready"})
    for state, outcome in (
        ("accepted", "verified"),
        ("failed", "failed"),
        ("blocked", "blocked"),
    ):
        terminal = {**candidate_ready, "state": state, "outcome": outcome}
        assert_invalid(validator, terminal)
        assert_valid(
            validator,
            {**terminal, "evidence_refs": ["artifact://ui-delivery-18/result.json"]},
        )


def test_blocked_and_failed_tasks_can_terminate_before_a_candidate_exists(
    repo_root: Path,
) -> None:
    validator = schema(task_schema_path(repo_root))
    terminal = {
        "task_id": "ui-delivery-19",
        "design_revision": "stitch-revision-73",
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


def test_review_schema_binds_read_only_verdict_to_exact_candidate_evidence(
    repo_root: Path,
) -> None:
    validator = schema(review_schema_path(repo_root))
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

    assert_valid(validator, review)
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
