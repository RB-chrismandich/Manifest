"""Shared fixtures and assertions for UI delivery contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def frontmatter(path: Path) -> dict[str, Any]:
    _, metadata, _ = path.read_text(encoding="utf-8").split("---", 2)
    document = yaml.safe_load(metadata)
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




def assert_no_response_format_conditionals(document: Any) -> None:
    if isinstance(document, dict):
        assert not {"allOf", "if", "then"} & document.keys()
        properties = document.get("properties")
        if properties is not None:
            assert isinstance(properties, dict)
            for name, property_schema in properties.items():
                assert isinstance(property_schema, dict), name
                assert "type" in property_schema, name
        for value in document.values():
            assert_no_response_format_conditionals(value)
    elif isinstance(document, list):
        for value in document:
            assert_no_response_format_conditionals(value)
def capture_recipe() -> dict[str, Any]:
    return {
        "id": "checkout-capture",
        "check_id": "checkout-ui",
        "artifacts": [{"path": "artifacts/checkout.png", "type": "image"}],
    }
