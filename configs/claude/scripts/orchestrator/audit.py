"""Append-only JSONL audit trail (FR-029) with mandatory redaction (FR-038).  [US5]

Follows the skillclaw_audit.py pattern: one append-only audit-<run>.jsonl per
run under a chmod 700 state dir, fail-open for observability. Every write is
routed through redact.scrub first so no secret is ever durably persisted.
"""
from __future__ import annotations


def append(*_args, **_kwargs):  # pragma: no cover - US5
    raise NotImplementedError("audit.append lands in US5 (T041)")
