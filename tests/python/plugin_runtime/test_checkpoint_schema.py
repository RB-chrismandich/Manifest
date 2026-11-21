"""Regression tests for checkpoint schema defaults and strict validation."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

pytest_plugins = ("tests.python.plugin_runtime.session_continuity_helpers",)


def test_schema_defaults_never_manufacture_authorization_or_success(runtime) -> None:
    helpers = importlib.import_module(
        "tests.python.plugin_runtime.session_continuity_helpers"
    )
    checkpoint = runtime._defaults_for_extended_fields(helpers._checkpoint())

    assert checkpoint["authorization"] == {
        "granted": [],
        "restrictions": [],
        "source": "",
        "observed_at": "",
    }
    assert set(checkpoint["completion"]["stages"].values()) == {"not_required"}


def test_schema_rejects_unknown_fields(runtime, state_home: Path) -> None:
    helpers = importlib.import_module(
        "tests.python.plugin_runtime.session_continuity_helpers"
    )
    checkpoint = helpers._checkpoint()
    checkpoint["unexpected"] = "must not be persisted"

    with pytest.raises(runtime.CheckpointValidationError, match="unknown fields"):
        runtime.write_checkpoint(checkpoint, state_home)


@pytest.mark.parametrize("version", (None, "1", 3, True))
def test_checkpoint_envelope_version_is_verified_before_the_body(
    runtime, state_home: Path, version: object
) -> None:
    """The digest covers the body only, so the version is attacker-writable."""
    helpers = importlib.import_module(
        "tests.python.plugin_runtime.session_continuity_helpers"
    )
    path = runtime.write_checkpoint(helpers._checkpoint(), state_home)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if version is None:
        envelope.pop("schema_version")
    else:
        envelope["schema_version"] = version
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(runtime.IntegrityError) as error:
        runtime.read_checkpoint(path)

    assert "schema version" in str(error.value)


_REDACTED_CONTEXT = {
    "requested_endpoint": "Fix issue #42",
    "authorization": {
        "granted": ["edit owned files"],
        "restrictions": ["no publish"],
        "source": "user request",
        "observed_at": "2026-11-12T10:00:00Z",
    },
    "targets": {"repository": "org/repo", "branch": "fix/42"},
    "artifacts": ["artifact://evidence-17"],
    "verified_facts": [
        {
            "fact": "CI passed for 012345",
            "provenance": "pipeline 17",
            "observed_at": "2026-11-12T10:01:00Z",
        }
    ],
    "outstanding_operations": [
        {
            "operation": "monitor pipeline",
            "owner": "primary",
            "blockers": ["awaiting runner"],
            "next_step": "check pipeline 17",
        }
    ],
    "completion": {
        "stages": {
            "implemented": True,
            "committed": "unknown",
            "pushed": "not_required",
            "ci_verified": True,
            "merged": "not_required",
            "deployed": "not_required",
            "live_validated": "not_required",
        },
        "evidence_refs": [
            {
                "stage": "ci_verified",
                "reference": "pipeline/17",
                "commit_sha": "012345",
            }
        ],
    },
    "blockers": ["awaiting runner"],
}
_REDACTED_CONTEXT_FIELDS = (
    "requested_endpoint",
    "authorization",
    "targets",
    "artifacts",
    "verified_facts",
    "outstanding_operations",
    "completion",
    "blockers",
)


def test_checkpoint_v2_redacted_context_round_trips(runtime, state_home: Path) -> None:
    helpers = importlib.import_module(
        "tests.python.plugin_runtime.session_continuity_helpers"
    )
    checkpoint = helpers._checkpoint()
    checkpoint.update(_REDACTED_CONTEXT)

    restored = runtime.read_checkpoint(runtime.write_checkpoint(checkpoint, state_home))
    assert all(
        restored[field] == checkpoint[field] for field in _REDACTED_CONTEXT_FIELDS
    )
