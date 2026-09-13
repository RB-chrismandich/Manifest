"""Focused tests for branch-protection normalization and API error handling."""

from __future__ import annotations

import pytest

from manifest_agent import protection


def test_required_check_order_is_not_drift() -> None:
    """GitHub may return required checks in any order without changing policy."""
    proposed = {
        "required_status_checks": {
            "strict": True,
            "checks": [
                {"context": "Lint & Validate", "app_id": 15368},
                {"context": "Test", "app_id": 15368},
            ],
        }
    }
    live = {
        "required_status_checks": {
            "strict": True,
            "checks": list(reversed(proposed["required_status_checks"]["checks"])),
        }
    }

    assert protection.diff_settings(live, proposed) == []


def test_required_check_app_mismatch_is_drift() -> None:
    """A matching status name from another app cannot satisfy the policy."""
    proposed = {
        "required_status_checks": {"checks": [{"context": "Test", "app_id": 15368}]}
    }
    live = {"required_status_checks": {"checks": [{"context": "Test", "app_id": 42}]}}

    diffs = protection.diff_settings(live, proposed)

    assert [item.setting for item in diffs] == ["required_status_checks.checks"]


def test_duplicate_resolved_check_names_are_blocked() -> None:
    """Two jobs cannot share one required-check identity."""
    config = {"required_status_checks": {"jobs": ["lint", "test"]}}
    jobs = {
        "lint": protection.JobInfo("Checks", (), False),
        "test": protection.JobInfo("Checks", (), False),
    }

    with pytest.raises(protection.BlockedError, match="duplicate"):
        protection.resolve_contexts(config, jobs)


def test_build_payload_supports_disabled_reviews() -> None:
    """Checks-only solo mode sends null instead of an unattainable review gate."""
    config = protection.load_config(protection.DEFAULT_CONFIG_PATH)
    config["required_pull_request_reviews"] = None

    payload = protection.build_payload(config, ("Test",))

    assert payload["required_pull_request_reviews"] is None


def test_normalize_live_preserves_disabled_reviews() -> None:
    """An absent live review gate normalizes to null for idempotent comparison."""
    normalized = protection.normalize_live({"required_pull_request_reviews": None})

    assert normalized["required_pull_request_reviews"] is None


def test_non_404_error_mentioning_not_protected_is_blocked() -> None:
    """Incidental wording cannot make a non-404 API failure look absent."""

    def runner(args: tuple[str, ...], stdin_data: bytes) -> tuple[int, str, str]:
        del args, stdin_data
        return 1, "", "HTTP 500: endpoint is not protected by circuit breaker"

    result = protection.get_live(runner, "acme/example", "main")

    assert result.status == "blocked"
    assert result.live is None
