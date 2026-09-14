"""Shared harness for ui-delivery contract tests.

Split across test_ui_delivery_contract.py and test_ui_delivery_task_schema.py
so neither file grows past the C-SIZE/CON-002 file-line ceiling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

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


def frontmatter(path: Path) -> dict[str, Any]:
    _, document_yaml, _ = path.read_text(encoding="utf-8").split("---", 2)
    document = yaml.safe_load(document_yaml)
    assert isinstance(document, dict)
    return document


def schema(path: Path) -> Draft202012Validator:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document, format_checker=FormatChecker())


def assert_valid(validator: Draft202012Validator, instance: dict[str, Any]) -> None:
    assert not list(validator.iter_errors(instance))


def assert_invalid(validator: Draft202012Validator, instance: dict[str, Any]) -> None:
    assert list(validator.iter_errors(instance))


def with_check_recipe(task: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    recipe = task["approved_check_recipes"][0]
    return {**task, "approved_check_recipes": [{**recipe, **overrides}]}


def docker_check_recipe() -> dict[str, Any]:
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


def capture_recipe() -> dict[str, Any]:
    return {
        "id": "checkout-capture",
        "check_id": "checkout-ui",
        "artifacts": [{"path": "artifacts/checkout.png", "type": "image"}],
    }


def assert_no_response_format_conditionals(schema_node: Any) -> None:
    if isinstance(schema_node, dict):
        assert not {"allOf", "if", "then"} & schema_node.keys()
        properties = schema_node.get("properties")
        if properties is not None:
            assert isinstance(properties, dict)
            for property_name, property_schema in properties.items():
                assert isinstance(property_schema, dict), property_name
                assert "type" in property_schema, property_name
        for value in schema_node.values():
            assert_no_response_format_conditionals(value)
    elif isinstance(schema_node, list):
        for value in schema_node:
            assert_no_response_format_conditionals(value)


def task_schema_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "plugins/stitch-design/skills/ui-delivery/references/task.schema.json"
    )


def review_schema_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "plugins/stitch-design/skills/ui-verification/references/review.schema.json"
    )


def accepted_task() -> dict[str, Any]:
    return {
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


def stitch_grant() -> dict[str, Any]:
    return {
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
