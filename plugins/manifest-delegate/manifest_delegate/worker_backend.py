"""Backend attempt execution and durable result publication."""

import os
import time
import uuid
from dataclasses import dataclass

from manifest_model_policy import (
    FailureEvidence,
    FallbackAction,
    FallbackController,
    ModelFallbackMode,
    ResolvedModel,
    classify_failure,
)

from . import backend, constants, envelope, jobstore, process


@dataclass
class _AttemptResult:
    returncode: int | None = None
    raw_output: str = ""
    raw_stderr: str = ""
    pgid: int | None = None
    timed_out: bool = False
    session_ref: str | None = None
    truncated: bool = False
    failure: object | None = None
    task_failure_summary: str | None = None


def _allowlisted_task_failure(raw_output, entry, model):
    """Map typed task denials to stable summaries without provider text."""
    candidate = envelope.normalize_envelope(
        backend.extract_response_text(entry, raw_output), entry["id"], model
    )
    error = candidate.get("error")
    if not isinstance(error, str):
        return None
    lowered = error.lower()
    if "outside the workspace" in lowered:
        return "sandbox denied: target is outside the workspace"
    if "destructive command blocked" in lowered:
        return "sandbox denied: destructive command blocked"
    return None


def _confirm_fallback(message):
    """Ask only in a foreground text invocation; EOF safely rejects."""
    try:
        answer = input(f"delegate: {message}. Continue? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _build_backend_invocation(entry, write, model_tier, mapping, prompt_bytes):
    """Build argv and the bytes, if any, delivered through process stdin."""
    transport = (entry.get("input") or {}).get("transport", "stdin")
    invoke_mapping = dict(mapping)
    if transport == "argv":
        invoke_mapping["prompt"] = prompt_bytes.decode("utf-8")
    return (
        backend.build_invoke_argv(entry, write, model_tier, invoke_mapping),
        prompt_bytes,
    )


def _model_runtime(record):
    raw_chain = record.get("model_chain") or [
        {"tier": record.get("model") or "auto", "model": record.get("model")}
    ]
    chain = tuple(ResolvedModel(item["tier"], item.get("model")) for item in raw_chain)
    controller = FallbackController(
        chain,
        ModelFallbackMode(record.get("fallback_mode", "confirm")),
        interactive=bool(record.get("interactive_fallback")),
        confirm_callback=_confirm_fallback,
    )
    return chain, controller, list(record.get("model_attempts") or [])


def _fail_attempt_cap(store, job_id):
    def _attempt_cap(record):
        record["state"] = "failed"
        record["fallback_pending"] = False
        record["error"] = "four-attempt cumulative cap reached"
        return record

    return store.mutate(job_id, _attempt_cap)


def _attempt_invocation(entry, record, selected, mapping, prompt_bytes):
    resume_from = record.get("resume_from_session_ref")
    if not (resume_from and entry.get("resume")):
        return _build_backend_invocation(
            entry,
            record.get("write", False),
            selected.model_id,
            mapping,
            prompt_bytes,
        )
    invoke_mapping = dict(mapping)
    if (entry.get("input") or {}).get("transport", "stdin") == "argv":
        invoke_mapping["prompt"] = prompt_bytes.decode("utf-8")
    return (
        backend.build_resume_argv(
            entry,
            resume_from,
            record.get("write", False),
            selected.model_id,
            invoke_mapping,
        ),
        prompt_bytes,
    )


def _mark_backend_started(store, job_id, index, selected):
    current = store.read(job_id)

    def _backend_started(record):
        dispatch = record.get("dispatch")
        if not isinstance(dispatch, dict) or dispatch.get("phase") != "worker_owned":
            raise ValueError("worker does not own backend dispatch")
        dispatch = dict(dispatch)
        dispatch["phase"] = "backend_started"
        dispatch["model_index"] = index
        record["dispatch"] = dispatch
        # record["model"] is a TIER, not a provider model id: task_policy writes
        # the tier on the initial dispatch, and _model_runtime reads this field
        # back as a tier when rebuilding a chain for a resumed job. Writing the
        # resolved id here made a post-fallback resume build an invalid tier.
        # The resolved id is still recorded per attempt in model_attempts.
        record["model"] = selected.tier
        return record

    return store.mutate(
        job_id, _backend_started, expected_version=current.get("version")
    )


def _capture_attempt(entry, argv, prompt_bytes, job_dir, budget, store, job_id):
    captured = process._spawn_backend(
        entry,
        argv,
        prompt_bytes,
        job_dir,
        budget,
        on_pgid=process._make_pgid_persister(store, job_id),
    )
    if len(captured) == 5:
        returncode, raw_output, pgid, timed_out, session_ref = captured
        return _AttemptResult(
            returncode=returncode,
            raw_output=raw_output,
            pgid=pgid,
            timed_out=timed_out,
            session_ref=session_ref,
        )
    return _AttemptResult(*captured)


def _classify_attempt(entry, selected, result):
    if result.timed_out:
        return None
    if result.returncode == 0:
        candidate = envelope.normalize_envelope(
            backend.extract_response_text(entry, result.raw_output),
            entry["id"],
            selected.model_id,
        )
        if candidate.get("outcome") != "failure":
            result.failure = None
            result.task_failure_summary = None
            return None
        output_status = "malformed"
    else:
        result.task_failure_summary = _allowlisted_task_failure(
            result.raw_output, entry, selected.model_id
        )
        output_status = None
    evidence = FailureEvidence(
        provider=entry["id"],
        harness=entry["id"],
        exit_status=result.returncode,
        stdout=result.raw_output,
        stderr=result.raw_stderr,
        output_envelope_status=output_status,
        task_status="failed" if result.task_failure_summary else None,
        truncated=result.truncated,
    )
    result.failure = classify_failure(evidence)
    return evidence


def _return_dispatch_to_worker(store, job_id, session_ref=None):
    current = store.read(job_id)

    def _retry_owned(record):
        dispatch = dict(record.get("dispatch") or {})
        if dispatch.get("phase") != "backend_started":
            raise ValueError("backend dispatch state changed during retry")
        dispatch["phase"] = "worker_owned"
        record["dispatch"] = dispatch
        if isinstance(session_ref, str) and session_ref:
            record["resume_from_session_ref"] = session_ref
        return record

    return store.mutate(job_id, _retry_owned, expected_version=current.get("version"))


def _persist_pending_fallback(store, job_id, attempts, evidence, decision, index):
    recovery = {
        "recovery_id": uuid.uuid4().hex,
        "next_tier": decision.proposed.tier if decision.proposed else None,
        "next_index": index + 1,
        "requires_task_resubmission": True,
    }
    store.replace_owned_file(job_id, "output.txt", "")
    store.write_recovery(job_id, recovery)

    def _pending(record):
        record["state"] = "fallback_pending"
        record["fallback_pending"] = True
        record["model_attempts"] = attempts
        record["failure_summary"] = evidence.persisted_summary()
        record["recovery"] = recovery
        dispatch = dict(record.get("dispatch") or {})
        dispatch["phase"] = "terminal"
        record["dispatch"] = dispatch
        return record

    return store.mutate(job_id, _pending)


def _run_attempts(store, job_id, entry, record, prompt_bytes, chain, controller):
    job_dir = store.job_dir(job_id)
    mapping = {"output_file": os.path.join(job_dir, "output.txt")}
    budget = record.get("budget_seconds", backend.DEFAULT_BUDGET_SECONDS)
    deadline = time.monotonic() + budget
    attempts = list(record.get("model_attempts") or [])
    result = _AttemptResult()
    for index, selected in enumerate(chain):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result = _AttemptResult(timed_out=True)
            break
        argv, process_prompt = _attempt_invocation(
            entry, record, selected, mapping, prompt_bytes
        )
        record = _mark_backend_started(store, job_id, index, selected)
        result = _capture_attempt(
            entry, argv, process_prompt, job_dir, remaining, store, job_id
        )
        attempts.append(
            {
                "attempt_id": record.get("attempt_id"),
                "tier": selected.tier,
                "model": selected.model_id,
                "returncode": result.returncode,
            }
        )
        evidence = _classify_attempt(entry, selected, result)
        if result.timed_out or evidence is None:
            break
        decision = controller.decide(index, result.failure)
        if decision.action is FallbackAction.RETRY:
            record = _return_dispatch_to_worker(
                store, job_id, result.session_ref if entry.get("resume") else None
            )
            continue
        if decision.action is FallbackAction.NEEDS_CONFIRMATION:
            pending = _persist_pending_fallback(
                store, job_id, attempts, evidence, decision, index
            )
            return record, attempts, result, pending
        break
    return record, attempts, result, None


def _result_envelope(store, job_id, entry, record, result):
    succeeded = (
        result.returncode == 0 and not result.timed_out and result.failure is None
    )
    if succeeded:
        store.replace_owned_file(job_id, "output.txt", result.raw_output)
        response = envelope.normalize_envelope(
            backend.extract_response_text(entry, result.raw_output),
            entry["id"],
            record.get("model"),
        )
        return succeeded, response
    store.replace_owned_file(job_id, "output.txt", "")
    response = {
        "backend": entry["id"],
        "model": record.get("model"),
        "outcome": "failure",
        "error": result.task_failure_summary or "provider attempt failed",
        "failure_class": (
            result.failure.value if result.failure is not None else "timeout"
        ),
    }
    return succeeded, response


def _warn_missing_session(entry, result):
    if result.session_ref is None and entry.get("resume"):
        constants.err(
            "backend {!r} produced no capturable session id this run "
            "(session_id_capture found nothing); a follow-up will start fresh".format(
                entry["id"]
            )
        )


def _finish_job(store, job_id, attempts, result, response, succeeded):
    if result.timed_out:
        final_state = "timeout"
    elif succeeded:
        final_state = "completed"
    else:
        final_state = "failed"

    def _finish(record):
        if record.get("state") in jobstore.TERMINAL_STATES:
            return None
        record["state"] = final_state
        record["envelope"] = response
        record["pgid"] = result.pgid
        record["returncode"] = result.returncode
        record["model_attempts"] = attempts
        record["result_attempt_id"] = record.get("attempt_id")
        if isinstance(response.get("findings"), list):
            record["findings_attempt_id"] = record.get("attempt_id")
        dispatch = dict(record.get("dispatch") or {})
        dispatch["phase"] = "terminal"
        record["dispatch"] = dispatch
        record.pop("failure_summary", None)
        record.pop("recovery", None)
        if result.session_ref and succeeded:
            record["session_ref"] = result.session_ref
        return record

    finished = store.mutate(job_id, _finish)
    if finished.get("state") != "fallback_pending":
        store.clear_recovery(job_id)
    return finished


def _run_backend_and_finish(store, job_id, entry, record, prompt_bytes):
    """Run the bounded model chain and publish only durable safe output."""
    chain, controller, attempts = _model_runtime(record)
    if len(attempts) + len(chain) > 4:
        return _fail_attempt_cap(store, job_id)
    record, attempts, result, pending = _run_attempts(
        store, job_id, entry, record, prompt_bytes, chain, controller
    )
    if pending is not None:
        return pending
    succeeded, response = _result_envelope(store, job_id, entry, record, result)
    _warn_missing_session(entry, result)
    return _finish_job(store, job_id, attempts, result, response, succeeded)
