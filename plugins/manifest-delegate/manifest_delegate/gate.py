"""manifest-delegate: gate."""

import json
import os
import subprocess
import sys

from . import backend, config, jobstore, registry, review, worker

# Imported by name, not as `from . import envelope`: several functions here take
# a parameter called `envelope` (the dict), which would shadow the module.
from .envelope import validate_findings


def _gate_allow(reason=None, json_mode=False, cause=None):
    """Emit approval only for an explicit skip: disabled, guarded, or no edits."""
    if reason:
        sys.stderr.write(f"delegate: review gate skipped: {reason}\n")
        if not json_mode:
            print(json.dumps({"systemMessage": f"review gate skipped: {reason}"}))
    if json_mode:
        print(
            json.dumps(
                {"decision": "approve", "reason": cause or reason or "gate disabled"}
            )
        )
    return 0


_INFRA_REASON_CODES = frozenset(
    {
        "backend_error",
        "backend_unavailable",
        "gate_execution_failed",
        "invalid_review",
        "prompt_unavailable",
        "review_incomplete",
        "review_timeout",
        "transcript_unreadable",
        "working_tree_unavailable",
    }
)


def _gate_block_infra(reason, json_mode=False):
    """Emit one sanitized block when review evidence cannot be established."""
    reason_code = reason if reason in _INFRA_REASON_CODES else "gate_execution_failed"
    message = (
        f"Review gate could not verify this turn ({reason_code}); make no tool calls or "
        "edits; report the failure to the developer for a decision."
    )
    if not json_mode:
        sys.stderr.write(f"delegate: review gate blocked: {reason_code}\n")
    print(json.dumps({"decision": "block", "reason": message}))
    return 0


def _gate_resolve_backend(gate_cfg, backends, user_config, services_disabled):
    """Resolve and validate the gate backend. Returns (entry, error_reason)."""
    backend_id = gate_cfg.get("backend") or user_config.get("default_backend")
    entry = registry.resolve_backend(backends, backend_id)
    if entry is None:
        return None, f"unknown gate backend {backend_id!r}"
    execution = entry.get("execution")
    if execution is not None and (
        not isinstance(execution, dict) or execution.get("read_only") is False
    ):
        return None, "backend {} cannot guarantee read-only review".format(entry["id"])
    enabled, layer = config.effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if not enabled:
        return None, "backend {} disabled at {} layer".format(entry["id"], layer)
    argv_probe = backend.build_invoke_argv(
        entry, write=False, model_tier=None, mapping={}
    )
    missing = backend._executable_missing(argv_probe)
    if missing:
        return None, "backend {} unavailable ({})".format(entry["id"], missing)
    return entry, None


_GATE_PROMPT_INSTRUCTIONS = (
    "You are an adversarial code reviewer gating a Stop hook. Review the diff "
    "below for defects that must block the turn from ending: security "
    "vulnerabilities, correctness bugs, swallowed exceptions, and broken "
    "contracts. Do not make edits; only report findings.\n\n"
    "End your final message with exactly one fenced JSON block (```json ... ```), "
    "and nothing after it, matching this shape:\n"
    "```json\n"
    "{\n"
    '  "backend": "<your backend id>",\n'
    '  "model": "<model or null>",\n'
    '  "outcome": "success" | "partial" | "failure",\n'
    '  "attempted": "<what you reviewed>",\n'
    '  "changes": [],\n'
    '  "succeeded": [],\n'
    '  "failed": [],\n'
    '  "follow_ups": [],\n'
    '  "findings": [{"severity": "critical|high|medium|low|info", "text": "<finding>"}]\n'
    "}\n"
    "```\n"
    'Set "findings" to [] when the diff has no blocking issues. Every element of '
    '"findings" MUST have string "severity" and "text" fields.\n\n'
    "Diff to review:\n\n"
)


def _gate_build_prompt(entry):
    """Assemble and size-check the gate review prompt. Returns (prompt, prompt_bytes, error_reason)."""
    try:
        diff = review.assemble_review_diff("auto", None, cwd=None)
    except (OSError, ValueError, RuntimeError, review.ReviewDiffError):
        return None, None, "could not assemble review diff"
    prompt = _GATE_PROMPT_INSTRUCTIONS + diff
    prompt_bytes = prompt.encode("utf-8")
    limit_error = backend.check_payload_limits(entry, prompt_bytes)
    if limit_error:
        return None, None, limit_error
    return prompt, prompt_bytes, None


def _gate_validate_findings(envelope):
    """Validate the gate envelope's outcome/findings shape (G4).

    Thin wrapper over the shared envelope.validate_findings so the gate and the
    standalone `review` command reject an omitted/malformed result identically.
    Returns (findings, error_reason); error_reason set (findings None) when the
    envelope is missing/malformed so the caller surfaces an explicit
    systemMessage instead of silently allowing.
    """
    return validate_findings(envelope, label="gate review")


def _gate_format_block(findings):
    """Format ranked findings into a Stop-hook block decision payload."""
    ranked = sorted(
        findings, key=lambda f: review._SEVERITY_RANK.get(f.get("severity", "info"), 5)
    )
    lines = [
        "{}: {}".format(f.get("severity", "info"), f.get("text", "")) for f in ranked
    ]
    reason = (
        "Review gate found issues before this turn ends:\n- "
        + "\n- ".join(lines)
        + "\n\nDo not make any tool calls or edits in response to this. "
        "Relay these findings to the developer and ask how to proceed — "
        "developer decides."
    )
    return {"decision": "block", "reason": reason}


def cmd_gate(args, backends, user_config, services_disabled):
    """`gate` — Stop-hook review gate (US4): blocks the turn end on findings."""
    json_mode = getattr(args, "json", False)

    if getattr(args, "stop_hook_active", False):
        return _gate_allow(json_mode=json_mode, cause="stop-hook-active")

    gate_cfg = dict(user_config.get("review_gate", {}))
    if getattr(args, "enable_review_gate_for_test", False):
        gate_cfg["enabled"] = True
    if not gate_cfg.get("enabled"):
        return _gate_allow(json_mode=json_mode, cause="gate disabled")

    try:
        edits_present, bash_used = _finishing_turn_tool_use(args.transcript)
    except (OSError, UnicodeError, ValueError):
        return _gate_block_infra("transcript_unreadable", json_mode=json_mode)
    # Dedicated edit tools are the clear signal. Shell-mediated changes also
    # require review when git proves the tree changed. If git cannot establish
    # that fact, uncertainty blocks instead of being misreported as no edits.
    if not edits_present:
        if not bash_used:
            return _gate_allow(json_mode=json_mode, cause="no code edits")
        tree_changed = _working_tree_has_changes()
        if tree_changed is None:
            return _gate_block_infra("working_tree_unavailable", json_mode=json_mode)
        if not tree_changed:
            return _gate_allow(json_mode=json_mode, cause="no code edits")

    entry, error_reason = _gate_resolve_backend(
        gate_cfg, backends, user_config, services_disabled
    )
    if error_reason:
        return _gate_block_infra("backend_unavailable", json_mode=json_mode)

    prompt, prompt_bytes, error_reason = _gate_build_prompt(entry)
    if error_reason:
        return _gate_block_infra("prompt_unavailable", json_mode=json_mode)

    budget = min(
        backend.resolve_budget(entry, user_config, gate_cfg.get("budget_seconds")),
        config.GATE_BUDGET_CAP_SECONDS,
    )
    store = jobstore.JobStore()
    return _gate_execute(
        store, entry, prompt, prompt_bytes, budget, json_mode, args.transcript
    )


def _gate_execute(store, entry, prompt, prompt_bytes, budget, json_mode, transcript):
    """Run the gate backend and turn its envelope into an allow/block
    decision. The job record is created here (not earlier in cmd_gate) so a
    gate that short-circuits on an early check never leaves a queued job
    behind (G8)."""
    record = store.create("gate", extra={"kind": "gate", "transcript": transcript})
    job_id = record["job_id"]
    jobstore._write_0600(os.path.join(store.job_dir(job_id), "prompt.txt"), prompt)

    def _claim_running(rec):
        rec["state"] = "running"
        rec["backend"] = entry["id"]
        rec["budget_seconds"] = budget
        return rec

    record = store.mutate(job_id, _claim_running)

    try:
        final = worker._run_backend_foreground(
            store, job_id, entry, record, prompt_bytes
        )
    # This is the security boundary: an unexpected reviewer/runtime failure is
    # uncertainty and therefore a block. Never relay the exception text.
    except Exception:  # constitution: exempt C-ERR -- fail-closed gate boundary
        return _gate_block_infra("gate_execution_failed", json_mode=json_mode)
    if final.get("state") == "timeout":
        return _gate_block_infra("review_timeout", json_mode=json_mode)

    envelope = final.get("envelope") or {}
    if envelope.get("error"):
        return _gate_block_infra("backend_error", json_mode=json_mode)

    findings, error_reason = _gate_validate_findings(envelope)
    if error_reason:
        return _gate_block_infra("invalid_review", json_mode=json_mode)
    if not findings:
        if envelope.get("outcome") == "success":
            return _gate_allow(json_mode=json_mode, cause="no findings")
        return _gate_block_infra("review_incomplete", json_mode=json_mode)

    print(json.dumps(_gate_format_block(findings)))
    return 0


_EDIT_TOOL_NAMES = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _iter_transcript_entries(transcript_path):
    """Yield strict JSONL objects and reject empty or malformed transcripts."""
    saw_entry = False
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("malformed transcript JSONL") from exc
            if not isinstance(entry, dict):
                raise ValueError("transcript entry is not an object")
            saw_entry = True
            yield entry
    if not saw_entry:
        raise ValueError("empty transcript")


def _is_tool_result_carrier(entry):
    content = entry.get("message", {}).get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _tool_use_names(entry):
    content = entry.get("message", {}).get("content")
    if not isinstance(content, list):
        return ()
    return tuple(
        b.get("name")
        for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use"
    )


def _finishing_turn_tool_use(transcript_path):
    """(edit_tools_used, bash_used) in the finishing turn — one streaming pass.

    The finishing turn is every entry after the last user message that is not a
    tool-result carrier. Holds only two booleans: a non-carrier user message
    resets both (a new finishing turn begins); an edit-tool or a Bash tool_use
    after it sets the matching flag; the flags at EOF are the answer."""
    edits = bash = False
    for entry in _iter_transcript_entries(transcript_path):
        etype = entry.get("type")
        if etype == "user" and not _is_tool_result_carrier(entry):
            edits = bash = False
            continue
        if etype != "assistant":
            continue
        names = _tool_use_names(entry)
        edits = edits or any(n in _EDIT_TOOL_NAMES for n in names)
        bash = bash or ("Bash" in names)
    return edits, bash


def _finishing_turn_has_edits(transcript_path):
    """True iff the finishing turn used a dedicated edit tool (Edit/Write/
    MultiEdit/NotebookEdit). Kept as the edit-tool predicate for callers/tests;
    Bash is handled separately (see cmd_gate)."""
    return _finishing_turn_tool_use(transcript_path)[0]


def _working_tree_has_changes(cwd=None):
    """Return change state, or ``None`` when git cannot make the observation."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return bool(proc.stdout.strip())
