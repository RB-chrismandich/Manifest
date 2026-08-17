"""Bounded, provider-aware failure evidence and classification."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

STREAM_LIMIT = 64 * 1024
FIELD_LIMIT = 4 * 1024
FIELD_COUNT_LIMIT = 32
EVIDENCE_LIMIT = 64 * 1024
SUMMARY_FIELD_LIMIT = 512
SUMMARY_LIMIT = 4 * 1024


class FailureClass(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    CAPACITY = "capacity"
    QUOTA = "quota"
    BILLING = "billing"
    AUTH = "auth"
    CONFIG = "config"
    SAFETY = "safety"
    MALFORMED_OUTPUT = "malformed_output"
    TASK_ERROR = "task_error"
    UNKNOWN = "unknown"


FALLBACK_ELIGIBLE = frozenset(
    {
        FailureClass.MODEL_UNAVAILABLE,
        FailureClass.RATE_LIMIT,
        FailureClass.TRANSIENT,
        FailureClass.CAPACITY,
        FailureClass.QUOTA,
        FailureClass.BILLING,
    }
)


@dataclass(frozen=True)
class FailureEvidence:
    provider: str
    harness: str
    exit_status: int | None = None
    structured_fields: Mapping[str, str] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    output_envelope_status: str | None = None
    task_status: str | None = None
    truncated: bool = False

    def __post_init__(self) -> None:
        for stream_name in ("stdout", "stderr"):
            value = getattr(self, stream_name)
            if len(value.encode("utf-8", errors="replace")) > STREAM_LIMIT:
                object.__setattr__(
                    self,
                    stream_name,
                    value.encode()[:STREAM_LIMIT].decode("utf-8", "ignore"),
                )
                object.__setattr__(self, "truncated", True)
        fields: dict[str, str] = {}
        total = 0
        for index, (key, value) in enumerate(self.structured_fields.items()):
            if index >= FIELD_COUNT_LIMIT:
                object.__setattr__(self, "truncated", True)
                break
            encoded = str(value).encode("utf-8", errors="replace")
            if len(encoded) > FIELD_LIMIT:
                object.__setattr__(self, "truncated", True)
                encoded = encoded[:FIELD_LIMIT]
            total += len(encoded)
            if total > EVIDENCE_LIMIT:
                object.__setattr__(self, "truncated", True)
                break
            fields[str(key)] = encoded.decode("utf-8", "ignore")
        object.__setattr__(self, "structured_fields", fields)

    def persisted_summary(self) -> dict[str, str | int | None]:
        """Return only allowlisted, value-bounded, secret-free durable fields."""
        summary = {
            "provider": self.provider
            if self.provider in _TRUSTED_IDENTITIES
            else "unknown",
            "harness": self.harness
            if self.harness in _TRUSTED_IDENTITIES
            else "unknown",
            "exit_status": self.exit_status,
            "output_envelope_status": _safe(self.output_envelope_status or ""),
            "task_status": _safe(self.task_status or ""),
            "truncated": "true" if self.truncated else "false",
        }
        payload = 0
        bounded = {}
        for key, value in summary.items():
            if isinstance(value, str):
                value = value.encode()[:SUMMARY_FIELD_LIMIT].decode("utf-8", "ignore")
                payload += len(value.encode())
            if payload > SUMMARY_LIMIT:
                break
            bounded[key] = value
        return bounded


_SECRET = re.compile(r"(?i)(?:bearer\s+\S+|sk-[a-z0-9_-]+|api[_-]?key\s*[=:]\s*\S+)")
_TRUSTED_IDENTITIES = frozenset(
    {"claude", "codex", "gemini", "cursor", "antigravity", "devin"}
)
_SDK_FIELD_NAMES = frozenset({"code", "status", "status_code", "type"})
_BLOCKING_PATTERNS = (
    (
        FailureClass.AUTH,
        r"\b(?:unauthenticated|unauthorized|invalid api key|not logged in|401|403)\b",
    ),
    (
        FailureClass.CONFIG,
        r"\b(?:invalid config|configuration error|unknown option|invalid model config)\b",
    ),
    (
        FailureClass.SAFETY,
        r"\b(?:safety|unsafe request|policy refusal|content filter)\b",
    ),
)
_ELIGIBLE_PATTERNS = (
    (
        FailureClass.MODEL_UNAVAILABLE,
        r"\b(?:model (?:is )?(?:unavailable|unsupported|not found)|unknown model|not_found|404)\b",
    ),
    (
        FailureClass.RATE_LIMIT,
        r"\b(?:rate limit|rate_limit_error|too many requests|429)\b",
    ),
    (
        FailureClass.BILLING,
        r"\b(?:payment required|billing|billing_error|402)\b",
    ),
    (
        FailureClass.QUOTA,
        r"\b(?:insufficient quota|insufficient_quota|quota exceeded|quota_exceeded|credit exhausted)\b",
    ),
    (
        FailureClass.CAPACITY,
        r"\b(?:capacity|overloaded|overloaded_error|resource exhausted|resource_exhausted)\b",
    ),
    (
        FailureClass.TRANSIENT,
        r"\b(?:temporarily unavailable|service unavailable|unavailable|gateway timeout|502|503|504)\b",
    ),
)


def _safe(value: str) -> str:
    return _SECRET.sub("[REDACTED]", value)


def _combined(evidence: FailureEvidence) -> str:
    if (
        evidence.provider not in _TRUSTED_IDENTITIES
        or evidence.harness not in _TRUSTED_IDENTITIES
    ):
        return ""
    fields = " ".join(
        f"{key}={value}" for key, value in evidence.structured_fields.items()
    )
    # stdout can contain the assistant answer. It is retained separately only
    # for the active attempt and is never provider-failure evidence.
    return f"{fields} {evidence.stderr}".lower()


def _match_failure(
    text: str, patterns: tuple[tuple[FailureClass, str], ...]
) -> FailureClass | None:
    for classification, pattern in patterns:
        if re.search(pattern, text):
            return classification
    return None


def sdk_failure_evidence(
    provider: str, harness: str, error: Exception
) -> FailureEvidence:
    """Extract only bounded status identities from known SDK exception shapes.

    Exception messages and arbitrary provider payload fields are deliberately
    excluded. The returned fields remain ephemeral and are never part of the
    persisted summary.
    """
    fields: dict[str, str] = {}

    def retain(prefix: str, value: object) -> None:
        if callable(value):
            try:
                value = value()
            except Exception:
                return
        if isinstance(value, StrEnum):
            value = value.value
        elif hasattr(value, "name") and isinstance(value.name, str):
            value = value.name
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            fields[prefix] = str(value)

    for name in _SDK_FIELD_NAMES:
        retain(name, getattr(error, name, None))
    response = getattr(error, "response", None)
    if response is not None:
        for name in ("status", "status_code"):
            retain(f"response_{name}", getattr(response, name, None))
    nested_error = getattr(error, "error", None)
    if nested_error is not None:
        for name in _SDK_FIELD_NAMES:
            value = (
                nested_error.get(name)
                if isinstance(nested_error, Mapping)
                else getattr(nested_error, name, None)
            )
            retain(f"error_{name}", value)
    body = getattr(error, "body", None)
    if isinstance(body, Mapping):
        nested = body.get("error")
        if isinstance(nested, Mapping):
            for name in _SDK_FIELD_NAMES:
                retain(f"body_{name}", nested.get(name))
    return FailureEvidence(provider, harness, structured_fields=fields)


def classify_failure(
    evidence: FailureEvidence | int | None,
    stderr: str = "",
    error: Exception | None = None,
    *,
    provider: str = "unknown",
    harness: str = "unknown",
) -> FailureClass:
    """Classify only bounded evidence; blocking evidence dominates fallback cues."""
    if not isinstance(evidence, FailureEvidence):
        evidence = FailureEvidence(provider, harness, evidence, stderr=stderr)
    if evidence.truncated:
        return FailureClass.UNKNOWN
    envelope = (evidence.output_envelope_status or "").lower()
    task = (evidence.task_status or "").lower()
    text = _combined(evidence)
    if envelope and envelope not in {"ok", "complete", "completed"}:
        return FailureClass.MALFORMED_OUTPUT
    if task and task not in {"ok", "complete", "completed", "not_started"}:
        return FailureClass.TASK_ERROR
    if blocking := _match_failure(text, _BLOCKING_PATTERNS):
        return blocking
    if eligible := _match_failure(text, _ELIGIBLE_PATTERNS):
        return eligible
    if error is not None and isinstance(error, (TimeoutError, ConnectionError)):
        return FailureClass.TRANSIENT
    return FailureClass.UNKNOWN
