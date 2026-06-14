"""Secret/credential/PII redaction (FR-038), reusing skillclaw_scrub.py.

Composes the repo's canonical secret patterns (skillclaw_scrub.redact_text) with
extra credential/PII patterns, then recursively scrubs any string inside a
structure. Invoked as a MANDATORY pre-write hook inside audit.append so no
durable write can bypass it (FR-038).
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

try:                                    # reuse the canonical pattern set
    from skillclaw_scrub import redact_text as _base_redact   # type: ignore
except Exception:                       # pragma: no cover - fallback if unavailable
    def _base_redact(text: str) -> str:
        return text

# Additional credential/PII patterns layered on top of the base set (FR-038).
_EXTRA = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),                       # GitHub PAT
    re.compile(r"gho_[A-Za-z0-9]{20,}"),                       # GitHub OAuth
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),                   # GitLab PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),                           # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),   # email (PII)
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*['\"]?([A-Za-z0-9._\-]{8,})"),
]


def redact_text(text: str) -> str:
    """Redact all known secret/credential/PII patterns in a string."""
    out = _base_redact(text)
    for pat in _EXTRA:
        if pat.groups == 2:
            out = pat.sub(lambda m: m.group(1) + "=" + REDACTED, out)
        else:
            out = pat.sub(REDACTED, out)
    return out


def scrub(value: Any) -> Any:
    """Recursively redact strings inside dicts/lists/strings (FR-038)."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value
