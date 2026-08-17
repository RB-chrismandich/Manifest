from pathlib import Path
from types import SimpleNamespace

import pytest
from manifest_model_policy import (
    FailureClass,
    FailureEvidence,
    ModelFallbackMode,
    ModelPolicyError,
    classify_failure,
    parse_skill_model_policy,
    resolve_chain,
    sdk_failure_evidence,
)


def test_frontmatter_normalizes_agy_and_preserves_order(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\nmodels:\n  agy: [advanced, flash, auto]\n"
        "model_fallback: {mode: confirm}\n---\nbody\n",
        encoding="utf-8",
    )
    policy = parse_skill_model_policy(skill)
    assert policy.chains["antigravity"] == ("advanced", "flash", "auto")
    assert policy.fallback_mode is ModelFallbackMode.CONFIRM


def test_frontmatter_rejects_nonfinal_auto(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nmodels:\n  codex: [auto, flash]\n---\n", encoding="utf-8")
    with pytest.raises(ModelPolicyError, match="final"):
        parse_skill_model_policy(skill)


def test_resolution_keeps_ids_centralized() -> None:
    config = {
        "model_tiers": {"codex": {"advanced": "gpt-x"}},
        "cli_agents": {"codex": {"model_args": ["--model", "{model}"]}},
    }
    assert resolve_chain(config, "codex", ("advanced", "auto"))[1].model_id is None


def test_truncated_evidence_is_unknown_and_summary_omits_raw_values() -> None:
    evidence = FailureEvidence("codex", "codex", stderr="x" * (64 * 1024 + 1))
    assert classify_failure(evidence) is FailureClass.UNKNOWN
    assert "stderr" not in evidence.persisted_summary()


def test_blocking_auth_dominates_rate_limit_text() -> None:
    evidence = FailureEvidence(
        "codex", "codex", stderr="HTTP 429 then unauthorized invalid API key"
    )
    assert classify_failure(evidence) is FailureClass.AUTH


def test_stdout_answer_text_is_never_failure_evidence() -> None:
    evidence = FailureEvidence(
        "codex",
        "codex",
        stdout="The answer discusses HTTP 429 and billing, but succeeded.",
    )
    assert classify_failure(evidence) is FailureClass.UNKNOWN


def test_untrusted_provider_text_is_not_classified() -> None:
    evidence = FailureEvidence("custom", "custom", stderr="HTTP 429 rate limit")
    assert classify_failure(evidence) is FailureClass.UNKNOWN


@pytest.mark.parametrize(
    ("provider", "attributes", "expected"),
    (
        (
            "claude",
            {
                "status_code": 429,
                "body": {"error": {"type": "rate_limit_error"}},
            },
            FailureClass.RATE_LIMIT,
        ),
        (
            "gemini",
            {"code": "insufficient_quota", "status": "RESOURCE_EXHAUSTED"},
            FailureClass.QUOTA,
        ),
        (
            "claude",
            {"response": SimpleNamespace(status_code=402)},
            FailureClass.BILLING,
        ),
        (
            "claude",
            {"body": {"error": {"type": "overloaded_error"}}},
            FailureClass.CAPACITY,
        ),
        (
            "gemini",
            {"response": SimpleNamespace(status=503)},
            FailureClass.TRANSIENT,
        ),
        (
            "gemini",
            {"code": lambda: SimpleNamespace(name="RESOURCE_EXHAUSTED")},
            FailureClass.CAPACITY,
        ),
        (
            "claude",
            {"error": SimpleNamespace(type="overloaded_error")},
            FailureClass.CAPACITY,
        ),
    ),
)
def test_sdk_exception_shapes_use_only_structured_status_fields(
    provider: str, attributes: dict[str, object], expected: FailureClass
) -> None:
    secret_message = "provider detail sk-secret-do-not-retain"
    error_type = type("ProviderSDKError", (RuntimeError,), {})
    error = error_type(secret_message)
    for name, value in attributes.items():
        setattr(error, name, value)

    evidence = sdk_failure_evidence(provider, provider, error)

    assert classify_failure(evidence) is expected
    assert secret_message not in str(dict(evidence.structured_fields))
    assert secret_message not in str(evidence.persisted_summary())
    assert "stderr" not in evidence.persisted_summary()
