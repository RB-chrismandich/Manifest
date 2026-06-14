"""Secret/credential/PII redaction (FR-038), reusing skillclaw_scrub.py.

Composes the repo's canonical secret patterns (skillclaw_scrub.redact_text) with
extra credential/PII patterns, then recursively scrubs any string inside a
structure. Invoked as a MANDATORY pre-write hook inside audit.append so no
durable write can bypass it (FR-038).

The canonical key/token/header patterns are ALSO duplicated into `_EXTRA` below,
so redaction stays safe even when `skillclaw_scrub` is not importable (e.g. when
daemon.py is run directly and sys.path[0] is the orchestrator dir, not its
parent). The import failure is logged loudly rather than silently degrading.
"""

from __future__ import annotations

import re
import sys
from typing import Any

REDACTED = "[REDACTED]"

try:                                    # reuse the canonical pattern set when available
    from skillclaw_scrub import redact_text as _base_redact   # type: ignore
except ImportError:                     # narrow: only an import problem, never mask real bugs
    print("orchestrator.redact: skillclaw_scrub unavailable — relying on built-in patterns "
          "(secret coverage still enforced via _EXTRA)", file=sys.stderr)

    def _base_redact(text: str) -> str:
        return text

# Credential/PII patterns. The first block duplicates skillclaw_scrub's canonical
# set so the fallback path above remains safe (FR-038 must never silently weaken).
_EXTRA = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),                   # Anthropic key
    re.compile(r"sk-proj-[A-Za-z0-9_-]{8,}"),                  # OpenAI project key
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),                      # generic sk- key
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),                       # GitHub PAT
    re.compile(r"gho_[A-Za-z0-9]{20,}"),                       # GitHub OAuth
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),                   # GitLab PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),                           # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),   # email (PII)
]
# Header-style secrets: capture the label, redact the value (group 2).
_HEADER = [
    re.compile(r"(?i)(authorization:\s*bearer\s+)(\S+)"),
    re.compile(r"(?i)(x-api-key:\s*)(\S+)"),
    re.compile(r"(?i)(anthropic-api-key:\s*)(\S+)"),
]
# key=value / key: value assignments. Value class covers the full base64 alphabet
# (+ / =) and there is no length floor — the label itself signals sensitivity.
# The separator + optional quote are preserved so the audit stays readable.
_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password)(\s*[=:]\s*['\"]?)([A-Za-z0-9+/=._-]+)"
)


def redact_text(text: str) -> str:
    """Redact all known secret/credential/PII patterns in a string."""
    out = _base_redact(text)
    for pat in _EXTRA:
        out = pat.sub(REDACTED, out)
    for pat in _HEADER:
        out = pat.sub(lambda m: m.group(1) + REDACTED, out)
    out = _ASSIGN.sub(lambda m: m.group(1) + m.group(2) + REDACTED, out)
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
