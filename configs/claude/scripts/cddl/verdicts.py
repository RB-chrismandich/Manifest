"""Fail-closed critic-verdict parsing (FR-006, research D5).

Contract: specs/482-critic-dev-loop/contracts/verdict-format.md. The scanner is
fence-aware: a ``cddl-verdict`` opener nested inside another fenced block (an
example the critic quotes) is content, never a verdict. Anything short of the
last well-formed block strictly validating is non-approval.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PHASE_DECISIONS = {1: {"complete", "questions"}, 2: {"approve", "reject"}}

_FENCE = re.compile(r"^(`{3,})(.*)$")


@dataclass
class Verdict:
    role: str
    decision: str | None
    findings: list = field(default_factory=list)
    parsed_ok: bool = False
    error: str | None = None
    raw_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "decision": self.decision,
            "findings": self.findings,
            "parsed_ok": self.parsed_ok,
            "error": self.error,
            "raw_path": self.raw_path,
        }


def extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Return (info_string, content) for every top-level fenced block.

    Tracks fence length so an inner shorter fence inside e.g. a ````markdown
    block never opens or closes anything (fail-closed against verdict/candidate
    spoofing). Closing fences must be bare (no info string), per CommonMark.
    """
    blocks: list[tuple[str, str]] = []
    fence_len = 0
    info = ""
    lines: list[str] = []
    for line in (text or "").splitlines():
        match = _FENCE.match(line.strip())
        if fence_len == 0:
            if match:
                fence_len = len(match.group(1))
                info = match.group(2).strip()
                lines = []
        elif match and len(match.group(1)) >= fence_len and not match.group(2).strip():
            blocks.append((info, "\n".join(lines)))
            fence_len = 0
        else:
            lines.append(line)
    return blocks


def strip_fenced_blocks(text: str) -> str:
    """Return only the lines OUTSIDE top-level fenced blocks (fence markers
    excluded). Same fence-length semantics as extract_fenced_blocks."""
    outside: list[str] = []
    fence_len = 0
    for line in (text or "").splitlines():
        match = _FENCE.match(line.strip())
        if fence_len == 0:
            if match:
                fence_len = len(match.group(1))
            else:
                outside.append(line)
        elif match and len(match.group(1)) >= fence_len and not match.group(2).strip():
            fence_len = 0
    return "\n".join(outside)


def parse_verdict(raw: str, expected_role: str, phase: int) -> Verdict:
    """Parse the LAST cddl-verdict block; any defect is non-approval."""

    def refuse(error: str) -> Verdict:
        return Verdict(role=expected_role, decision=None, error=error)

    candidates = [c for info, c in extract_fenced_blocks(raw) if info == "cddl-verdict"]
    if not candidates:
        return refuse("no cddl-verdict block found in the response")
    try:
        obj = json.loads(candidates[-1])
    except json.JSONDecodeError as exc:
        return refuse(f"cddl-verdict block is not strict JSON: {exc}")
    if not isinstance(obj, dict):
        return refuse("cddl-verdict must be a single JSON object")

    role = obj.get("role")
    decision = obj.get("decision")
    findings = obj.get("findings", [])
    if role != expected_role:
        return refuse(
            f"verdict role {role!r} does not match invoked role {expected_role!r}"
        )
    if decision not in PHASE_DECISIONS.get(phase, set()):
        return refuse(f"decision {decision!r} is not valid in phase {phase}")
    if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
        return refuse("findings must be a list of objects")
    if decision in ("reject", "questions") and not findings:
        return refuse(f"decision {decision!r} requires non-empty findings")

    return Verdict(role=role, decision=decision, findings=findings, parsed_ok=True)
