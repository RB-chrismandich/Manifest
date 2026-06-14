#!/usr/bin/env python3
"""Autonomous Issue Implementation Orchestrator — daemon entry point.

The daemon owns all execution, Git/API calls, polling, timeouts, and audit
persistence; the decision engine only decides. It drives ONE issue at a time
through the six phases to a clean PR (spec: Assumptions — single active issue).

MVP scope: Phase 1 (prioritization) dispatch + dry-run. Later phases (US2–US5)
extend dispatch with gates, consensus, audit, and the resolution loop.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:                                    # importable as a package and runnable as a script
    from . import engine, pipeline, gates, consensus, redact, audit
except ImportError:                     # pragma: no cover - direct `python daemon.py`
    import engine, pipeline, gates, consensus, redact, audit   # type: ignore

SCRIPTS_DIR = Path(__file__).resolve().parents[1]   # configs/claude/scripts
GIT_OPS = SCRIPTS_DIR / "git_ops.sh"
AUDIT_DIR = "~/.claude/state/orchestrator"          # orchestrator.yml audit.dir


def err(*msg: object) -> None:
    print("orchestrator:", *msg, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Platform-agnostic issue reads via git_ops.sh (R7). Live calls only; tests use
# fixtures and never reach this path.
# --------------------------------------------------------------------------- #
def _normalize_issue(raw: dict) -> dict:
    """Map a `gh`/`glab` issue object to the engine's shape.

    gh uses `number` (not `id`) and labels as objects ({name,...}); depends_on
    is not a native tracker field, so it defaults to [] (richer dependency
    ingestion is future work)."""
    labels = [lab.get("name", lab) if isinstance(lab, dict) else lab
              for lab in raw.get("labels", [])]
    iid = raw.get("id") or (f"#{raw['number']}" if raw.get("number") is not None else "")
    return {
        "id": iid,
        "title": raw.get("title", ""),
        "body": raw.get("body", ""),
        "labels": labels,
        "depends_on": raw.get("depends_on", []),
    }


def fetch_issues(repo: str) -> list[dict]:
    """Fetch open issues for the repo through git_ops.sh (github/gitlab/git)."""
    if not GIT_OPS.exists():
        err(f"git_ops.sh not found at {GIT_OPS}")
        return []
    # subcommand is `issue-list`; gh/glab require an explicit --json field list.
    proc = subprocess.run(
        [str(GIT_OPS), "issue-list", "--repo", repo, "--json", "number,title,body,labels"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        err(f"issue-list failed: {proc.stderr.strip()}")
        return []
    try:
        return [_normalize_issue(i) for i in json.loads(proc.stdout or "[]")]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        err(f"could not parse issues JSON: {exc}")
        return []


# --------------------------------------------------------------------------- #
# Phase dispatch
# --------------------------------------------------------------------------- #
def dispatch_phase1(issues: list[dict]) -> dict:
    """Run the Phase 1 prioritization core and return a validated envelope."""
    result = engine.prioritize(issues)
    trace = [f"{len(issues)} issue(s) ingested; {len(result.held_issue_ids)} held by no-automation."]
    cycle = pipeline.detect_cycle(issues)
    if cycle:
        return engine.blocked_envelope(
            1, f"dependency cycle detected: {' -> '.join(cycle)}",
            bs_type="contradictory_input", trace=trace,
        )
    envelope = {
        "phase": 1, "status": "ok", "payload": result.to_payload(),
        "reasoning_log": trace + [result.top_choice_justification], "escalation": None,
    }
    errs = engine.validate_envelope(envelope)
    if errs:                                    # contract self-check (FR-001)
        return engine.blocked_envelope(1, f"engine produced invalid envelope: {errs}", trace=trace)
    return envelope


def _apply_consensus(phase: int, payload: dict, base_trace: list[str], votes: list[bool] | None):
    """Cross-verify a gate decision (FR-034). Returns an envelope: low band escalates,
    medium proceeds with a flagged trace, high/absent proceeds cleanly."""
    if not votes:
        return engine.ok_envelope(phase, payload, base_trace)
    result = consensus.evaluate(votes)
    trace = base_trace + [f"consensus: {result.to_summary()}"]
    if result.escalate:                  # <50% agreement → human (FR-034)
        return engine.escalation_envelope(
            phase, f"gate consensus below threshold ({result.agreement_ratio:.0%})", trace=trace)
    if result.band == "medium":
        trace.append("disagreements highlighted as advisory (medium consensus)")
    return engine.ok_envelope(phase, payload, trace)


def dispatch_analysis_gate(findings: list[dict], votes: list[bool] | None = None) -> dict:
    """Phase 4: fail-closed analysis gate, cross-verified (FR-017/019, FR-034)."""
    payload = gates.evaluate_analysis_gate(findings)
    trace = [f"analysis: {len(findings)} finding(s); gate={payload['gate']}."]
    return _apply_consensus(4, payload, trace, votes)


def dispatch_verification_gate(findings: list[dict], votes: list[bool] | None = None) -> dict:
    """Phase 5: Tier-1-fail-closed verification gate, cross-verified (FR-030/033, FR-034)."""
    payload = gates.evaluate_verification_gate(findings)
    label = gates.advisory_verdict_label(findings)
    trace = [f"verification: verdict={payload['verdict']} ({label}); "
             f"pr_open_approved={payload['pr_open_approved']}."]
    return _apply_consensus(5, payload, trace, votes)


def handle_control_flags(phase: int, state, *, critical_failure: bool = False,
                         resource_available: bool = True):
    """Pre-dispatch control checks. Returns an envelope to short-circuit, or None.

    - critical_failure flag => needs_escalation (FR-025).
    - agents token/credit exhausted => transient pause, mark state paused WITHOUT
      incrementing the attempt count (FR-035); the daemon resumes the same phase.
    """
    if critical_failure:
        return engine.escalation_envelope(phase, "daemon signaled a critical failure",
                                          bs_type="critical_failure")
    if not resource_available:
        if state is not None:
            state.pause_for_resource()          # FR-035: no attempt increment
        return engine.blocked_envelope(
            phase, "cross-verification agents token/credit exhausted; pausing for resume",
            transient=True, bs_type="resource_unavailable",
            trace=["resource pause: will re-invoke this phase on the hourly poll (FR-035)"])
    return None


def dispatch_phase2(decisions: list[dict], finalized_params: dict | None = None,
                    open_questions: list[str] | None = None) -> dict:
    """Phase 2: arbitrate engine vs agy per decision; log conflicts (FR-011/012)."""
    conflicts, chosen = [], {}
    for d in decisions:
        pick, conflict = engine.arbitrate(d["topic"], d["engine_choice"], d.get("agy_choice"))
        chosen[d["topic"]] = pick.get("label")
        if conflict:
            conflicts.append(conflict)
    payload = {
        "finalized_spec_parameters": finalized_params if finalized_params is not None else chosen,
        "agy_conflicts": conflicts,
        "open_questions": list(open_questions or []),
    }
    trace = [f"phase2: {len(decisions)} decision(s), {len(conflicts)} agy conflict(s)."]
    return engine.ok_envelope(2, payload, trace)


def dispatch_phase6(modifications: list[dict], pr_reply: str, ci_root_cause: str | None = None) -> dict:
    """Phase 6: PR resolution — modifications + reply (must end with ✅/🛠️, FR-022)."""
    if not engine.pr_reply_has_marker(pr_reply):
        return engine.blocked_envelope(6, "PR reply missing confirmation marker ✅/🛠️ (FR-022)",
                                       bs_type="contradictory_input")
    payload = {"modifications": modifications, "pr_reply": pr_reply, "ci_root_cause": ci_root_cause}
    trace = [f"phase6: {len(modifications)} modification(s); "
             f"root_cause={'identified' if ci_root_cause else 'none'}."]
    return engine.ok_envelope(6, payload, trace)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="orchestrator",
        description="Drive one issue through the orchestrator pipeline to a clean PR.",
    )
    p.add_argument("--repo", help="owner/repo to operate on")
    p.add_argument("--phase", type=int, choices=range(1, 7), metavar="1-6", help="run a single phase")
    p.add_argument("--payload", help="path to a JSON inputs fixture (offline dispatch)")
    p.add_argument("--dry-run", action="store_true", help="decide only; no side effects")
    return p


def _new_run_id() -> str:
    """A short, unique-enough run id without importing uuid into the hot path."""
    import uuid
    return uuid.uuid4().hex[:12]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.payload:                            # offline single-phase dispatch
        inputs = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        issues = inputs.get("issues", [])
    elif args.repo:
        if args.dry_run:                        # --dry-run promises no side effects;
            err("--dry-run requires --payload (no live tracker reads in dry-run mode)")
            return 2                            # ...so it must not hit the live tracker
        issues = fetch_issues(args.repo)
    else:
        err("provide --repo or --payload")
        return 2

    phase = args.phase or 1
    if phase == 1:
        envelope = dispatch_phase1(issues)
    else:
        err(f"phase {phase} dispatch not yet implemented (MVP covers phase 1)")
        return 3

    # FR-029/SC-010: persist every response to the durable, redacted audit trail.
    # Skipped under --dry-run (an audit write is a side effect).
    if not args.dry_run:
        try:
            audit.AuditLog(AUDIT_DIR, _new_run_id()).record_response(envelope)
        except Exception as exc:                # fail-open: never crash on audit
            err(f"audit persist failed (continuing): {exc}")

    print(json.dumps(redact.scrub(envelope), indent=2))   # FR-038: redact before emitting
    return 0 if envelope["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
