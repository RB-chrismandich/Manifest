"""Secret/credential/PII redaction (FR-038), reusing skillclaw_scrub.py.  [US5]

Mandatory pre-write hook inside audit.append so no durable write can bypass it.
"""
from __future__ import annotations


def scrub(*_args, **_kwargs):  # pragma: no cover - US5
    raise NotImplementedError("redact.scrub lands in US5 (T042)")
