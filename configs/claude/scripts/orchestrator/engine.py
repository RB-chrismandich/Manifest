"""Stateless decision-engine adapter.

The engine holds NO state between invocations (FR-006): everything it needs
arrives in the context payload, and every invocation returns exactly one
response envelope (FR-001). This module provides the deterministic, testable
core — envelope validation, severity derivation, context-payload construction,
and the Phase 1 prioritization core — plus a pluggable backend protocol so the
live LLM call (via parallel_agent.py) is injectable and tests stay deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

SCHEMA_DIR = Path(__file__).parent / "schemas"

# Ordered severity scale (spec FR-036). Index = rank weight (higher = more severe).
SEVERITY_ORDER = ["low", "medium", "high", "critical"]
VALID_STATUS = {"ok", "blocked", "needs_escalation"}
BLOCK_LABEL = "no-automation"


# --------------------------------------------------------------------------- #
# Schema loading + envelope validation (FR-001, FR-002, FR-004, FR-005)
# --------------------------------------------------------------------------- #
def load_schema(name: str) -> dict[str, Any]:
    """Load a JSON Schema by file stem (e.g. 'response-envelope')."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_envelope(obj: Any) -> list[str]:
    """Validate a response envelope against the contract. Returns a list of
    error strings (empty == valid). Pure-Python so the daemon needs no extra
    dependency; enforces the invariants the LLM contract must never violate.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["envelope is not a JSON object"]

    required = {"phase", "status", "payload", "reasoning_log", "escalation"}
    missing = required - obj.keys()
    if missing:
        errors.append(f"missing required keys: {sorted(missing)}")
    extra = obj.keys() - required
    if extra:
        errors.append(f"unexpected keys outside envelope: {sorted(extra)}")  # FR-002

    phase = obj.get("phase")
    if not isinstance(phase, int) or not 1 <= phase <= 6:
        errors.append("phase must be an integer 1..6")

    status = obj.get("status")
    if status not in VALID_STATUS:
        errors.append(f"status must be one of {sorted(VALID_STATUS)}")

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")

    rlog = obj.get("reasoning_log")
    if not isinstance(rlog, list) or not all(isinstance(s, str) for s in rlog):
        errors.append("reasoning_log must be a list of strings")  # FR-004

    esc = obj.get("escalation")
    if status == "ok":
        if payload == {} and obj.get("phase"):  # ok with empty payload is suspicious but allowed
            pass
        if esc is not None:
            errors.append("escalation MUST be null when status == ok")
    else:
        # blocked / needs_escalation: payload empty + escalation populated (FR-005)
        if payload != {}:
            errors.append("payload MUST be {} when status != ok (FR-005)")
        if not isinstance(esc, dict):
            errors.append("escalation MUST be populated when status != ok (FR-005)")
        else:
            bs = esc.get("blocking_state")
            if not isinstance(esc.get("reason"), str):
                errors.append("escalation.reason must be a string")
            if not isinstance(bs, dict) or "transient" not in bs or "type" not in bs:
                errors.append("escalation.blocking_state must have type + transient")
    return errors


def blocked_envelope(phase: int, reason: str, *, transient: bool = False,
                     bs_type: str = "missing_input", trace: list[str] | None = None) -> dict[str, Any]:
    """Build a canonical blocked envelope (FR-005 / FR-035)."""
    return {
        "phase": phase,
        "status": "blocked",
        "payload": {},
        "reasoning_log": list(trace or []),
        "escalation": {"reason": reason, "blocking_state": {"type": bs_type, "transient": transient}},
    }


def escalation_envelope(phase: int, reason: str, *, bs_type: str = "low_consensus",
                        trace: list[str] | None = None) -> dict[str, Any]:
    """Build a canonical needs_escalation envelope (FR-025 / FR-034 low band)."""
    return {
        "phase": phase,
        "status": "needs_escalation",
        "payload": {},
        "reasoning_log": list(trace or []),
        "escalation": {"reason": reason, "blocking_state": {"type": bs_type, "transient": False}},
    }


def ok_envelope(phase: int, payload: dict[str, Any], trace: list[str]) -> dict[str, Any]:
    """Build a canonical ok envelope and self-check it against the contract (FR-001)."""
    env = {"phase": phase, "status": "ok", "payload": payload,
           "reasoning_log": list(trace), "escalation": None}
    errs = validate_envelope(env)
    if errs:
        return blocked_envelope(phase, f"engine produced invalid envelope: {errs}",
                                bs_type="invalid_envelope", trace=trace)
    return env


# --------------------------------------------------------------------------- #
# Severity derivation (FR-036): metadata-first, infer on absence
# --------------------------------------------------------------------------- #
def derive_severity(issue: dict[str, Any]) -> tuple[str, str]:
    """Return (severity, source) where source in {label, field, inferred}.

    Metadata-first: an explicit `severity` field or a `severity:<level>` /
    bare-level label wins; otherwise infer from the body. Always reports the
    source so the reasoning trace can record it (FR-036).
    """
    # 1) explicit field
    field_val = str(issue.get("severity", "")).strip().lower()
    if field_val in SEVERITY_ORDER:
        return field_val, "field"

    # 2) labels: only "severity:<level>" / "priority:<level>" or a bare level.
    #    A colon-delimited label with any OTHER prefix (e.g. "scope:high",
    #    "kind:critical") is NOT a severity assertion (FR-036; avoids the
    #    order-dependent misclassification that would break SC-002).
    for raw in issue.get("labels", []):
        token = str(raw).strip().lower()
        if ":" in token:
            prefix, level = token.split(":", 1)
            if prefix not in ("severity", "priority"):
                continue
        else:
            level = token
        if level in SEVERITY_ORDER:
            return level, "label"

    # 3) infer from body keywords (deterministic, conservative)
    body = str(issue.get("body", "")).lower()
    if any(k in body for k in ("security", "data loss", "crash", "outage", "vulnerab")):
        return "critical", "inferred"
    if any(k in body for k in ("broken", "fails", "error", "regression")):
        return "high", "inferred"
    if any(k in body for k in ("slow", "confusing", "minor")):
        return "medium", "inferred"
    return "low", "inferred"


def severity_rank(severity: str) -> int:
    """Higher == more severe; unknown sorts lowest."""
    return SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else -1


# --------------------------------------------------------------------------- #
# Context payload (daemon -> engine)
# --------------------------------------------------------------------------- #
def build_context_payload(phase: int, inputs: dict[str, Any], *, attempt: int = 1,
                          consensus: dict | None = None, critical_failure: bool = False,
                          resource_available: bool = True) -> dict[str, Any]:
    """Assemble the complete per-invocation input (data-model.md)."""
    return {
        "phase": phase,
        "inputs": inputs,
        "attempt": attempt,
        "consensus": consensus,
        "critical_failure": critical_failure,
        "resource_available": resource_available,
    }


# --------------------------------------------------------------------------- #
# Backend protocol (live LLM call injectable; tests use a deterministic fake)
# --------------------------------------------------------------------------- #
class Backend(Protocol):
    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the decision engine for one phase; return a response envelope."""
        ...


# --------------------------------------------------------------------------- #
# Phase 1 prioritization core (FR-008..FR-010, FR-037)
# --------------------------------------------------------------------------- #
@dataclass
class Prioritization:
    ranked_issue_ids: list[str]
    top_choice_justification: str
    dependency_notes: list[dict[str, Any]] = field(default_factory=list)
    held_issue_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ranked_issue_ids": self.ranked_issue_ids,
            "top_choice_justification": self.top_choice_justification,
            "dependency_notes": self.dependency_notes,
        }


def prioritize(issues: list[dict[str, Any]]) -> Prioritization:
    """Deterministic prioritization core mirrored by the Phase 1 skill prompt.

    Ranks implementable issues by (unblock-count, severity, id) so an issue that
    unblocks others out-ranks an isolated higher-severity one (FR-009). Issues
    bearing the no-automation label are excluded and reported as held (FR-037).
    """
    implementable = [i for i in issues if BLOCK_LABEL not in i.get("labels", [])]
    held = [i["id"] for i in issues if BLOCK_LABEL in i.get("labels", [])]

    # How many *implementable* issues each issue unblocks (reverse of depends_on).
    # Held (no-automation) issues never count toward the unblock score and never
    # leak into dependency_notes (FR-037 / FR-009): only edges among
    # implementable issues matter, since held issues can never be worked.
    impl_ids = {i["id"] for i in implementable}
    blocks: dict[str, list[str]] = {i["id"]: [] for i in implementable}
    for i in implementable:
        for dep in i.get("depends_on", []):
            if dep in impl_ids:
                blocks[dep].append(i["id"])

    def sort_key(issue: dict[str, Any]) -> tuple[int, int, str]:
        sev, _src = derive_severity(issue)
        return (-len(blocks.get(issue["id"], [])), -severity_rank(sev), str(issue["id"]))

    ranked = sorted(implementable, key=sort_key)
    ranked_ids = [i["id"] for i in ranked]
    dep_notes = [{"issue_id": iid, "blocks": sorted(b)} for iid, b in blocks.items() if b]

    if not ranked_ids:
        why = "No implementable issues: backlog empty or all candidates held by the no-automation label."
    else:
        top = ranked[0]
        sev, src = derive_severity(top)
        nblocks = len(blocks.get(top["id"], []))
        if nblocks:
            why = (f"Selected {top['id']}: unblocks {nblocks} issue(s), outranking isolated "
                   f"higher-severity items (FR-009). Severity {sev} (source: {src}).")
        else:
            why = f"Selected {top['id']}: highest severity {sev} (source: {src}); no inter-issue dependencies."
    return Prioritization(ranked_ids, why, dep_notes, held)


# --------------------------------------------------------------------------- #
# Phase 2 arbitration core (FR-011, FR-012) — engine vs agy
# --------------------------------------------------------------------------- #
def _option_score(opt: dict[str, Any]) -> tuple[int, int, int]:
    """Resolution order (FR-011): repo-consistency > modularity/safety > reversibility."""
    return (int(bool(opt.get("repo_consistent"))),
            int(bool(opt.get("secure")) or bool(opt.get("modular"))),
            int(bool(opt.get("reversible"))))


def arbitrate(topic: str, engine_choice: dict[str, Any],
              agy_choice: dict[str, Any] | None) -> tuple[dict[str, Any], dict | None]:
    """Arbitrate one decision between the engine and agy (FR-012).

    Returns (chosen, conflict_or_None). agy absent => proceed on the engine's
    choice with no conflict (FR-028 exemption). On a genuine divergence the
    higher-scoring option wins; ties do NOT defer to agy by default (FR-012).
    """
    if agy_choice is None or agy_choice.get("label") == engine_choice.get("label"):
        return engine_choice, None
    chosen = max((engine_choice, agy_choice), key=_option_score)  # stable: engine first on tie
    rejected = agy_choice if chosen is engine_choice else engine_choice
    conflict = {
        "topic": topic,
        "chosen": chosen.get("label"),
        "rejected": rejected.get("label"),
        "rationale": ("repo-consistency > modularity/safety > reversibility (FR-011); "
                      "ties retain the engine's choice (FR-012)."),
    }
    return chosen, conflict


# --------------------------------------------------------------------------- #
# Phase 6 PR-reply marker (FR-022)
# --------------------------------------------------------------------------- #
_CONFIRM_MARKERS = ("✅", "\U0001F6E0")   # ✅ , 🛠️ (allow trailing variation selector)


def pr_reply_has_marker(reply: str) -> bool:
    """True if the PR reply ends with a confirmation marker ✅ or 🛠️ (FR-022)."""
    stripped = reply.rstrip().rstrip("️").rstrip()
    return stripped.endswith(_CONFIRM_MARKERS)


# --------------------------------------------------------------------------- #
# Safety helpers (FR-005, FR-023, FR-024)
# --------------------------------------------------------------------------- #
_INJECTION_MARKERS = (
    "ignore your rules", "ignore previous", "disregard previous", "disregard your",
    "approve immediately", "bypass your rules", "bypass the gate", "bypass safety",
    "override your", "you must approve",
)
_DESTRUCTIVE = (
    "push --force", "push -f", "reset --hard", "filter-branch", "filter-repo",
    "rebase", "branch -d", "branch -D", "git gc --prune",
)


def scan_injection(untrusted: str) -> list[str]:
    """Return notes for any embedded directive in untrusted input (FR-023)."""
    low = untrusted.lower()
    return [f"ignored embedded directive: {m!r}" for m in _INJECTION_MARKERS if m in low]


def is_destructive(command: str) -> bool:
    return any(tok in command.lower() for tok in _DESTRUCTIVE)


def guard_destructive(command: str, no_upstream_human_work: bool) -> tuple[bool, str]:
    """Allow a destructive op only with explicit confirmation no human work is lost (FR-024).
    Returns (allowed, reason)."""
    if not is_destructive(command):
        return True, "non-destructive"
    if no_upstream_human_work:
        return True, "explicitly confirmed: no upstream human work would be lost"
    return False, "destructive op withheld: upstream human work not confirmed (FR-024) — escalating"


def require_inputs(phase: int, inputs: dict[str, Any], required: list[str],
                   trace: list[str] | None = None) -> dict[str, Any] | None:
    """Return a blocked envelope if any required input is missing (FR-005), else None.

    "Missing" means the key is absent — NOT present-but-falsy. An empty list/dict
    (e.g. a clean analysis `findings:[]` or an empty backlog `issues:[]`) is a
    valid input, not a missing one; call sites that need a non-empty string layer
    their own check.
    """
    missing = [k for k in required if k not in inputs]
    if missing:
        return blocked_envelope(phase, f"missing required input(s): {missing}",
                                bs_type="missing_input", trace=trace)
    return None
