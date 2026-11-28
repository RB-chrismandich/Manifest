"""Revalidation tests for checkpoint provenance and ownership continuity."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.python.plugin_runtime.session_continuity_helpers import _checkpoint
from tests.python.plugin_runtime.session_continuity_helpers import (
    repo_root as repo_root_fixture,  # noqa: F401 - register the pytest fixture
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    runtime as runtime_fixture,  # noqa: F401 - register the pytest fixture
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    state_home as state_home_fixture,  # noqa: F401 - register the pytest fixture
)


@pytest.mark.parametrize("field", ["source", "observed_at"])
@pytest.mark.parametrize("value", ["", "   "])
def test_populated_authorization_requires_provenance(
    runtime, state_home: Path, field: str, value: str
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["authorization"] = {
        "granted": ["edit owned files"],
        "restrictions": [],
        "source": "user request",
        "observed_at": "2026-11-12T10:00:00Z",
    }
    checkpoint["authorization"][field] = value

    with pytest.raises(
        runtime.CheckpointValidationError, match="required for populated"
    ):
        runtime.write_checkpoint(checkpoint, state_home)


@pytest.mark.parametrize(
    ("evidence", "targets"),
    [
        (
            {
                "stage": "ci_verified",
                "reference": "pipeline/17",
                "commit_sha": "abc123",
                "target": "other-repo",
                "branch": "main",
                "environment": "staging",
            },
            {"repository": "repo", "branch": "main", "environment": "staging"},
        ),
        (
            {
                "stage": "ci_verified",
                "reference": "pipeline/17",
                "commit_sha": "abc123",
                "target": "repo",
                "branch": "main",
                "environment": "staging",
            },
            {"repository": "repo", "branch": "release", "environment": "staging"},
        ),
        (
            {
                "stage": "ci_verified",
                "reference": "pipeline/17",
                "commit_sha": "abc123",
                "target": "repo",
                "branch": "main",
                "environment": "production",
            },
            {"repository": "repo", "branch": "main", "environment": "staging"},
        ),
    ],
)
def test_same_sha_ci_requires_matching_target_branch_and_environment(
    runtime, state_home: Path, evidence: dict, targets: dict
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["targets"] = targets
    checkpoint["completion"]["evidence_refs"] = [evidence]
    path = runtime.write_checkpoint(checkpoint, state_home)

    report = runtime.revalidate_continuation(
        path,
        checkpoint["repository"],
        checkpoint["live_operations"],
        {"granted": [], "restrictions": [], "source": "", "observed_at": ""},
    )

    assert report.trusted is False
    assert report.stale_ci_evidence == ("pipeline/17",)
    assert "CI evidence is stale for the current commit" in report.reconciliation_needs


def test_same_sha_ci_with_matching_target_branch_and_environment_is_trusted(
    runtime, state_home: Path
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["targets"] = {
        "repository": "repo",
        "branch": "main",
        "environment": "staging",
    }
    checkpoint["completion"]["evidence_refs"] = [
        {
            "stage": "ci_verified",
            "reference": "pipeline/17",
            "commit_sha": "abc123",
            "target": "repo",
            "branch": "main",
            "environment": "staging",
        }
    ]
    path = runtime.write_checkpoint(checkpoint, state_home)

    report = runtime.revalidate_continuation(
        path,
        checkpoint["repository"],
        checkpoint["live_operations"],
        {"granted": [], "restrictions": [], "source": "", "observed_at": ""},
    )

    assert report.trusted is True
    assert report.stale_ci_evidence == ()


def test_invalid_current_authorization_cannot_be_trusted(
    runtime, state_home: Path
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["authorization"] = {
        "granted": ["edit owned files"],
        "restrictions": [],
        "source": "user request",
        "observed_at": "2026-11-12T10:00:00Z",
    }
    path = runtime.write_checkpoint(checkpoint, state_home)

    report = runtime.revalidate_continuation(
        path,
        checkpoint["repository"],
        checkpoint["live_operations"],
        {
            **checkpoint["authorization"],
            "source": "",
        },
    )

    assert report.trusted is False
    assert "current authorization evidence is required" in report.reconciliation_needs


def test_revalidation_requires_current_authorization_evidence(
    runtime, state_home: Path
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["authorization"] = {
        "granted": ["edit owned files"],
        "restrictions": ["no publish"],
        "source": "user request",
        "observed_at": "2026-11-12T10:00:00Z",
    }
    path = runtime.write_checkpoint(checkpoint, state_home)
    report = runtime.revalidate_continuation(
        path, checkpoint["repository"], checkpoint["live_operations"]
    )

    assert report.trusted is False
    assert "current authorization evidence is required" in report.reconciliation_needs


def test_revalidation_detects_changed_authorization(runtime, state_home: Path) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["authorization"].update(
        {
            "granted": ["edit owned files"],
            "source": "user request",
            "observed_at": "2026-11-12T10:00:00Z",
        }
    )
    path = runtime.write_checkpoint(checkpoint, state_home)
    report = runtime.revalidate_continuation(
        path,
        checkpoint["repository"],
        checkpoint["live_operations"],
        {"granted": [], "restrictions": [], "source": "", "observed_at": ""},
    )

    assert report.trusted is False
    assert "authorization or access changed" in report.reconciliation_needs
    assert runtime.read_checkpoint(path)["authorization"] == checkpoint["authorization"]


def test_outstanding_operation_requires_current_linked_operation(
    runtime, state_home: Path
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["outstanding_operations"] = [
        {
            "operation": "monitor pipeline",
            "owner": "primary",
            "blockers": ["awaiting runner"],
            "next_step": "check pipeline 17",
        }
    ]
    path = runtime.write_checkpoint(checkpoint, state_home)
    report = runtime.revalidate_continuation(
        path, checkpoint["repository"], checkpoint["live_operations"]
    )

    assert report.trusted is False
    assert report.ownership_changes == ("monitor pipeline",)
    assert "live-operation ownership changed" in report.reconciliation_needs


def test_outstanding_operation_matches_current_link_and_owner(
    runtime, state_home: Path
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["outstanding_operations"] = [
        {
            "operation": "monitor pipeline",
            "owner": "primary",
            "blockers": ["awaiting runner"],
            "next_step": "check pipeline 17",
        }
    ]
    path = runtime.write_checkpoint(checkpoint, state_home)
    current = [
        {
            "owner": "primary",
            "handle": "job-17",
            "status": "running",
            "obligation": "Continue polling; never duplicate the job.",
            "operation": "monitor pipeline",
        },
    ]
    report = runtime.revalidate_continuation(path, checkpoint["repository"], current)

    assert report.trusted is True
    assert report.ownership_changes == ()


def test_outstanding_operation_detects_changed_current_owner(
    runtime, state_home: Path
) -> None:
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["outstanding_operations"] = [
        {
            "operation": "monitor pipeline",
            "owner": "primary",
            "blockers": ["awaiting runner"],
            "next_step": "check pipeline 17",
        }
    ]
    path = runtime.write_checkpoint(checkpoint, state_home)

    report = runtime.revalidate_continuation(
        path,
        checkpoint["repository"],
        [
            {
                "owner": "replacement-session",
                "handle": "job-17",
                "status": "running",
                "obligation": "Continue polling; never duplicate the job.",
                "operation": "monitor pipeline",
            },
        ],
    )

    assert report.trusted is False
    assert "monitor pipeline" in report.ownership_changes
    assert "live-operation ownership changed" in report.reconciliation_needs


@pytest.mark.parametrize("mismatch", [None, "target", "branch", "environment"])
def test_summary_template_evidence_uses_declared_targets(runtime, state_home, mismatch):
    import json

    template = (
        Path(__file__).resolve().parents[3]
        / "plugins/manifest-workspace/skills/session-checkpoint/references/summary-template.md"
    )
    example = json.loads(
        template.read_text().split("```json\n", 1)[1].split("```", 1)[0]
    )
    reference = example["completion"]["evidence_refs"][0]
    assert {"target", "branch", "environment", "commit_sha"} <= reference.keys()
    checkpoint = runtime._defaults_for_extended_fields(_checkpoint())
    checkpoint["targets"] = {
        "repository": "repo",
        "branch": "main",
        "environment": "staging",
    }
    reference.update(
        reference="template/pipeline",
        commit_sha=checkpoint["repository"]["head"],
        target="repo",
        branch="main",
        environment="staging",
    )
    if mismatch:
        reference[mismatch] = "different"
    checkpoint["completion"]["evidence_refs"] = [reference]
    path = runtime.write_checkpoint(checkpoint, state_home)
    result = runtime.revalidate_continuation(
        path,
        checkpoint["repository"],
        checkpoint["live_operations"],
        {"granted": [], "restrictions": [], "source": "", "observed_at": ""},
    )
    assert result.trusted is (mismatch is None)
    assert result.stale_ci_evidence == (
        () if mismatch is None else ("template/pipeline",)
    )
