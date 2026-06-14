"""Append-only JSONL audit trail (FR-029) with mandatory redaction (FR-038).

Follows the skillclaw_audit.py pattern: one append-only audit-<run>.jsonl per
run under a chmod 700 state dir, fail-open for observability. EVERY write is
routed through redact.scrub first so no secret is ever durably persisted — the
redaction is structural (inside this module), not a call-site convention.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from . import redact
except ImportError:                     # pragma: no cover - direct import
    import redact                       # type: ignore


class AuditLog:
    """Per-run append-only JSONL audit writer."""

    def __init__(self, state_dir: str | Path, run_id: str):
        self.dir = Path(state_dir).expanduser()
        self.run_id = run_id
        self.path = self.dir / f"audit-{run_id}.jsonl"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        # idempotent + chmod 700 (Constitution V; spec security posture)
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:                 # pragma: no cover - non-POSIX
            pass

    def append(self, record: dict[str, Any]) -> bool:
        """Redact then append one JSONL line. Fail-open: a write failure logs a
        warning and returns False rather than crashing the pipeline (FR-029)."""
        safe = redact.scrub(record)     # FR-038 — mandatory, cannot be bypassed
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(safe, sort_keys=True) + "\n")
            return True
        except OSError as exc:          # fail-open for observability
            print(f"orchestrator: audit write failed (continuing): {exc}", file=sys.stderr)
            return False

    def record_response(self, envelope: dict[str, Any]) -> bool:
        """Persist a full response envelope (FR-029 / SC-010). Includes `payload`
        so the per-phase decision content (ranked ids, tasks, verdict, modifications,
        pr_reply) is recoverable — append() redacts the whole record first (FR-038)."""
        return self.append({
            "run_id": self.run_id,
            "phase": envelope.get("phase"),
            "status": envelope.get("status"),
            "payload": envelope.get("payload", {}),
            "reasoning_log": envelope.get("reasoning_log", []),
            "escalation": envelope.get("escalation"),
        })
