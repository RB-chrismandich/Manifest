"""Schema-level contracts for UI delivery Stitch grants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.python.plugin_runtime.ui_delivery_contract_support import (
    assert_invalid,
    assert_valid,
    capture_recipe,
    docker_check_recipe,
    schema,
)

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
                "argv": ["npm", "run", "test:ui", "--", "CheckoutCard"],
                "timeout_ms": 120000,
                "backend": "sandbox-exec",
                "artifacts": [{"path": "artifacts/checkout-ui.xml", "type": "junit"}],
            }
        ],
        "capture_recipes": [capture_recipe()],
        "model_route": "@ui_review",
        "repair_cycles": 2,
        "evidence_refs": ["artifact://ui-delivery-17/review.json"],
        "outcome": "verified",
    }


def _stitch_grant() -> dict[str, Any]:
    return {
        "project_id": "stitch-project-17",
        "expires_at": "2030-01-01T00:00:00Z",
        "mutations": [
            {
                "tool_name": "mcp__stitch_edit_screens",
                "input_hash": "sha256:" + "8" * 64,
                "max_uses": 1,
                "expected_readback": {
                    "tool_name": "mcp__stitch_get_screen",
                    "response_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                },
            }
        ],
        "readback_tools": ["mcp__stitch_get_screen"],
    }


def _validator(repo_root: Path) -> Draft202012Validator:
    return schema(
        repo_root
        / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )


def test_grant_schema_requires_single_use_mutations(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()
    grant = _stitch_grant()

    assert_invalid(
        validator,
        {
            **task,
            "stitch_grant": {
                **grant,
                "mutations": [{**grant["mutations"][0], "max_uses": 2}],
            },
        },
    )


def test_grant_schema_requires_authorized_readbacks(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()
    grant = _stitch_grant()
    mutation = grant["mutations"][0]
    without_readback = {
        key: value for key, value in mutation.items() if key != "expected_readback"
    }

    assert_invalid(
        validator,
        {**task, "stitch_grant": {**grant, "mutations": [without_readback]}},
    )
    assert_invalid(
        validator,
        {
            **task,
            "stitch_grant": {
                **grant,
                "mutations": [
                    {
                        **mutation,
                        "expected_readback": {
                            **mutation["expected_readback"],
                            "tool_name": "mcp__stitch_list_projects",
                        },
                    }
                ],
            },
        },
    )
    for projectless_read in (
        "mcp__stitch_list_projects",
        "mcp__stitch_read_url_content",
    ):
        assert_invalid(
            validator,
            {**task, "stitch_grant": {**grant, "readback_tools": [projectless_read]}},
        )


def test_grant_schema_requires_canonical_hashes_and_tools(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()
    grant = _stitch_grant()
    mutation = grant["mutations"][0]

    for noncanonical_hash in (
        "sha256:8d5f2e",
        "SHA256:" + "a" * 64,
        "sha256:" + "A" * 64,
    ):
        assert_invalid(
            validator,
            {
                **task,
                "stitch_grant": {
                    **grant,
                    "mutations": [{**mutation, "input_hash": noncanonical_hash}],
                },
            },
        )
    for noncanonical_response_hash in (
        "SHA256:" + "a" * 64,
        "sha256:" + "A" * 64,
    ):
        assert_invalid(
            validator,
            {
                **task,
                "stitch_grant": {
                    **grant,
                    "mutations": [
                        {
                            **mutation,
                            "expected_readback": {
                                **mutation["expected_readback"],
                                "response_hash": noncanonical_response_hash,
                            },
                        }
                    ],
                },
            },
        )
    assert_invalid(validator, {**task, "candidate_hash": "sha256:" + "A" * 64})
    assert_invalid(
        validator,
        {
            **task,
            "stitch_grant": {
                **grant,
                "mutations": [{**mutation, "tool_name": "stitch.edit_screen"}],
            },
        },
    )
    assert_invalid(
        validator,
        {**task, "stitch_grant": {**grant, "readback_tools": ["stitch.get_screen"]}},
    )


def test_grant_schema_requires_valid_expiration(repo_root: Path) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()

    assert_invalid(
        validator,
        {**task, "stitch_grant": {**_stitch_grant(), "expires_at": "not-a-date"}},
    )


def test_grant_schema_accepts_readback_for_existing_project(repo_root: Path) -> None:
    validator = _validator(repo_root)

    assert_valid(validator, {**_accepted_task(), "stitch_grant": _stitch_grant()})


def test_grant_schema_aligns_predictable_readbacks_with_runtime(
    repo_root: Path,
) -> None:
    validator = _validator(repo_root)
    task = _accepted_task()
    create_grant = {
        "expires_at": "2030-01-01T00:00:00Z",
        "mutations": [
            {
                "tool_name": "mcp__stitch_create_project",
                "input_hash": "sha256:" + "c" * 64,
                "max_uses": 1,
                "expected_readback": {
                    "tool_name": "mcp__stitch_get_project",
                    "predictable_fields": {"title": "Checkout"},
                    "resource_identity": "project",
                },
            }
        ],
        "readback_tools": ["mcp__stitch_get_project"],
    }

    assert_valid(validator, {**task, "stitch_grant": create_grant})
    assert_invalid(
        validator,
        {**task, "stitch_grant": {**create_grant, "project_id": "project-17"}},
    )
    for expected_readback in (
        {
            "tool_name": "mcp__stitch_get_project",
            "response_hash": "sha256:" + "a" * 64,
        },
        {
            "tool_name": "mcp__stitch_get_project",
            "predictable_fields": {"title": "Checkout"},
        },
        {
            "tool_name": "mcp__stitch_get_project",
            "predictable_fields": {"title": "Checkout"},
            "resource_identity": "screen",
        },
        {
            "tool_name": "mcp__stitch_get_project",
            "response_hash": "sha256:" + "a" * 64,
            "predictable_fields": {"title": "Checkout"},
            "resource_identity": "project",
        },
    ):
        assert_invalid(
            validator,
            {
                **task,
                "stitch_grant": {
                    **create_grant,
                    "mutations": [
                        {**create_grant["mutations"][0], "expected_readback": expected_readback}
                    ],
                },
            },
        )

    predictable_existing = {
        **_stitch_grant(),
        "mutations": [
            {
                **_stitch_grant()["mutations"][0],
                "expected_readback": {
                    "tool_name": "mcp__stitch_get_screen",
                    "predictable_fields": {"title": "Checkout"},
                    "resource_identity": "screen",
                },
            }
        ],
    }
    assert_valid(validator, {**task, "stitch_grant": predictable_existing})
