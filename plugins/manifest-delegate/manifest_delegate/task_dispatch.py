"""Job creation, worker dispatch, and task result presentation."""

import json
import sys

from . import worker
from .task_resolution import _validated_second_opinion_context


def _create_dispatch_record(
    store, entry, extra, existing_record, second_opinion_record
):
    if existing_record is not None:
        return existing_record
    if second_opinion_record is None:
        return store.create(entry["id"], extra=extra)
    return store.create_second_opinion(
        second_opinion_record["job_id"],
        entry["id"],
        expected_version=second_opinion_record["version"],
        attempt_id=second_opinion_record["attempt_id"],
        findings_digest=second_opinion_record["findings_digest"],
        validator=_validated_second_opinion_context,
        extra=extra,
    )


def _queue_continuation(store, record):
    try:
        return (
            store.mutate(
                record["job_id"],
                lambda current: dict(current, state="queued"),
                expected_version=record["version"],
            ),
            None,
        )
    except ValueError as error:
        return None, f"delegate: {error}"


def _restore_continuation(store, record, recovery, failure_summary):
    if recovery is not None:
        worker._restore_fallback_pending(
            store, record["job_id"], recovery, failure_summary
        )


def _dispatch_background(
    store, args, entry, record, prompt_bytes, recovery, failure_summary
):
    try:
        worker._spawn_worker(store, record["job_id"], prompt_bytes)
    except Exception as error:
        _restore_continuation(store, record, recovery, failure_summary)
        print(
            f"delegate: worker dispatch failed ({type(error).__name__})",
            file=sys.stderr,
        )
        return 1
    if args.json:
        print(
            json.dumps(
                {"job_id": record["job_id"], "backend": entry["id"], "state": "queued"}
            )
        )
    else:
        print(f"job_id: {record['job_id']}")
        print(f"check: delegate.py status {record['job_id']}")
    return 0


def _run_foreground(store, entry, record, prompt_bytes, recovery, failure_summary):
    store.mutate(record["job_id"], lambda current: dict(current, state="running"))
    try:
        return (
            worker._run_backend_foreground(
                store, record["job_id"], entry, record, prompt_bytes
            ),
            None,
        )
    except Exception as error:
        _restore_continuation(store, record, recovery, failure_summary)
        return None, f"delegate: backend dispatch failed ({type(error).__name__})"


def _result_envelope(entry, record, final):
    response = final.get("envelope") or {}
    if final.get("state") == "fallback_pending":
        response = {
            "backend": entry["id"],
            "model": final.get("model"),
            "outcome": "fallback_pending",
            "job_id": record["job_id"],
            "version": final.get("version"),
            "model_attempts": final.get("model_attempts", []),
            "failure_summary": final.get("failure_summary", {}),
            "recovery": final.get("recovery", {}),
        }
    response.setdefault("job_id", record["job_id"])
    return response


def _print_fallback_resume(record, final):
    recovery = final.get("recovery") or {}
    print("state: fallback_pending")
    print(f"version: {final.get('version')}")
    print(f"recovery_id: {recovery.get('recovery_id')}")
    print(f"next_tier: {recovery.get('next_tier')}")
    print(
        "resume: delegate.py task --resume {} --expected-version {} "
        "--recovery-id {} --fallback-decision approve -".format(
            record["job_id"], final.get("version"), recovery.get("recovery_id")
        )
    )


def _print_foreground_result(args, entry, extra, record, final, response):
    if args.json:
        print(json.dumps(response))
        return
    print(f"job_id: {record['job_id']}")
    print(f"backend: {entry['id']}")
    if extra.get("second_opinion_of"):
        print(f"second_opinion_of: {extra['second_opinion_of']}")
    print(f"outcome: {response.get('outcome')}")
    if response.get("error"):
        print(f"error: {response['error']}")
    if final.get("state") == "fallback_pending":
        _print_fallback_resume(record, final)


def _dispatch_task(
    store,
    args,
    entry,
    model_tier,
    extra,
    prompt,
    prompt_bytes,
    existing_record=None,
    second_opinion_record=None,
):
    """Create a job and execute it in the requested ownership mode."""
    del prompt
    extra = dict(extra)
    record = _create_dispatch_record(
        store, entry, extra, existing_record, second_opinion_record
    )
    continuation = record.get("state") == "fallback_prepared"
    recovery = record.get("recovery") if continuation else None
    failure_summary = record.get("failure_summary") if continuation else None
    if continuation:
        record, error = _queue_continuation(store, record)
        if error:
            print(error, file=sys.stderr)
            return 2
    print(
        f"delegate: dispatching to backend {entry['id']!r} (model={model_tier})",
        file=sys.stderr,
    )
    if args.background:
        return _dispatch_background(
            store, args, entry, record, prompt_bytes, recovery, failure_summary
        )
    final, error = _run_foreground(
        store, entry, record, prompt_bytes, recovery, failure_summary
    )
    if error:
        print(error, file=sys.stderr)
        return 1
    response = _result_envelope(entry, record, final)
    _print_foreground_result(args, entry, extra, record, final, response)
    if final.get("state") == "timeout":
        return 1
    return 0 if response.get("outcome") != "failure" else 1
