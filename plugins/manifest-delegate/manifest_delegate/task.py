"""Task command orchestration and compatibility exports."""

import json
import sys

from . import backend, jobstore
from .task_dispatch import _dispatch_task as _dispatch_task
from .task_policy import (
    build_dispatch_extra,
    prepare_pending_resume,
    resolve_task_model_plan,
)
from .task_prompt import _PROMPT_SUMMARY_MAX_CHARS as _PROMPT_SUMMARY_MAX_CHARS
from .task_prompt import _build_task_extra as _build_task_extra
from .task_prompt import _build_task_prompt as _build_task_prompt
from .task_resolution import (
    _check_task_backend_ready as _check_task_backend_ready,
)
from .task_resolution import (
    _find_last_job_for_backend as _find_last_job_for_backend,
)
from .task_resolution import _resolve_job_id as _resolve_job_id
from .task_resolution import _resolve_sole_active as _resolve_sole_active
from .task_resolution import (
    _resolve_task_backend_entry as _resolve_task_backend_entry,
)
from .task_resolution import _resolve_task_resume as _resolve_task_resume
from .task_resolution import (
    _resolve_task_second_opinion as _resolve_task_second_opinion,
)
from .task_resolution import (
    _validated_second_opinion_context as _validated_second_opinion_context,
)
from .task_resolution import (
    _warn_if_second_opinion_same_backend as _warn_if_second_opinion_same_backend,
)


def _handle_fallback_rejection(store, args, resume_record):
    decision = getattr(args, "fallback_decision", None)
    if resume_record is not None and decision == "reject":
        expected = getattr(args, "expected_version", None)
        recovery_id = getattr(args, "recovery_id", None)
        if expected is None or not recovery_id:
            print(
                "delegate: rejecting fallback_pending requires --expected-version "
                "and --recovery-id",
                file=sys.stderr,
            )
            return 2
        try:
            rejected = store.reject_fallback(
                resume_record["job_id"],
                expected_version=expected,
                recovery_id=recovery_id,
                action="reject",
            )
        except (OSError, ValueError) as error:
            print(f"delegate: {error}", file=sys.stderr)
            return 2
        print(json.dumps(rejected) if args.json else "state: fallback_rejected")
        return 0
    if resume_record is not None and resume_record.get("state") == "fallback_rejected":
        print(
            "delegate: fallback recovery already resolved by a conflicting action",
            file=sys.stderr,
        )
        return 2
    return None


def _resolve_task_records(store, args, backends, user_config, resume_record):
    second_opinion, error = _resolve_task_second_opinion(store, args)
    if error:
        return None, None, None, error
    if second_opinion is not None and resume_record is not None:
        return None, None, None, "delegate: second opinion cannot also resume a job"
    entry, error = _resolve_task_backend_entry(
        args, backends, user_config, resume_record
    )
    return resume_record, second_opinion, entry, error


def _prepare_prompt_boundary(
    args,
    entry,
    user_config,
    services_disabled,
    second_opinion,
    plan,
):
    prompt, write, error = _build_task_prompt(args, second_opinion)
    if error:
        return None, None, None, error, 2
    if plan.pending_resume and not prompt.strip():
        return (
            None,
            None,
            None,
            ("delegate: resuming fallback_pending requires task resubmission"),
            2,
        )
    error, code = _check_task_backend_ready(
        entry, user_config, services_disabled, plan.model_tier
    )
    if error:
        return None, None, None, error, code
    prompt_bytes = prompt.encode("utf-8")
    limit_error = backend.check_payload_limits(entry, prompt_bytes)
    if limit_error:
        return None, None, None, f"delegate: {limit_error}", 2
    return prompt, write, prompt_bytes, None, None


def cmd_task(args, backends, user_config, services_disabled):
    """Validate, prepare, and dispatch one delegate task."""
    store = jobstore.JobStore()
    resume_record, error = _resolve_task_resume(store, args, backends, user_config)
    if error:
        print(error, file=sys.stderr)
        return 2
    handled = _handle_fallback_rejection(store, args, resume_record)
    if handled is not None:
        return handled
    resume_record, second_opinion, entry, error = _resolve_task_records(
        store, args, backends, user_config, resume_record
    )
    if error:
        print(error, file=sys.stderr)
        return 2
    _warn_if_second_opinion_same_backend(
        second_opinion, entry, backends, user_config, services_disabled
    )
    plan, error = resolve_task_model_plan(
        store, args, entry, user_config, resume_record
    )
    if error:
        print(error, file=sys.stderr)
        return 2
    prompt, write, prompt_bytes, error, code = _prepare_prompt_boundary(
        args, entry, user_config, services_disabled, second_opinion, plan
    )
    if error:
        print(error, file=sys.stderr)
        return code
    resume_record, error = prepare_pending_resume(store, args, resume_record, plan)
    if error:
        print(error, file=sys.stderr)
        return 2
    extra = build_dispatch_extra(
        args, entry, user_config, resume_record, second_opinion, plan, write
    )
    try:
        return _dispatch_task(
            store,
            args,
            entry,
            plan.model_tier,
            extra,
            prompt,
            prompt_bytes,
            existing_record=resume_record if plan.pending_resume else None,
            second_opinion_record=second_opinion,
        )
    except (OSError, ValueError) as error:
        print(f"delegate: second-opinion source changed: {error}", file=sys.stderr)
        return 2
