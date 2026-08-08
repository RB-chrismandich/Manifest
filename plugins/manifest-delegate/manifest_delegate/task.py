"""manifest-delegate: task."""

import json
import os
import sys

from . import backend, config, jobstore, readiness, registry, worker


def _resolve_job_id(store, prefix):
    ids = store.list_job_ids()
    if prefix in ids:
        return prefix, None
    matches = sorted(j for j in ids if j.startswith(prefix))
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"no job matches {prefix!r}"
    return None, "ambiguous job id {!r} matches: {}".format(prefix, ", ".join(matches))


def _resolve_sole_active(store):
    active = []
    for job_id in store.list_job_ids():
        try:
            rec = store.reap_if_dead(job_id)
        except (OSError, ValueError):
            continue
        if rec.get("state") in jobstore.NON_TERMINAL_STATES:
            active.append(job_id)
    if len(active) == 1:
        return active[0], None
    if not active:
        return None, "no active job"
    return None, "ambiguous: multiple active jobs: {}".format(", ".join(sorted(active)))


def _find_last_job_for_backend(store, backend_id):
    candidates = []
    for job_id in store.list_job_ids():
        try:
            rec = store.read(job_id)
        except (OSError, ValueError):
            continue
        if rec.get("backend") == backend_id and rec.get("session_ref"):
            candidates.append(rec)
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.get("updated_at", 0))
    return candidates[-1]


def _resolve_task_resume(store, args, backends, user_config):
    """Resolve --resume / --resume-last into (resume_record, error_message)."""
    if getattr(args, "resume", None):
        job_id, resume_error = _resolve_job_id(store, args.resume)
        if not job_id:
            return None, resume_error
        try:
            return store.read(job_id), None
        except (OSError, ValueError) as exc:
            return None, f"delegate: cannot read job {args.resume!r}: {exc}"
    if getattr(args, "resume_last", False):
        if args.backend:
            probe = registry.resolve_backend(backends, args.backend)
            probe_id = probe["id"] if probe else args.backend
        else:
            probe_id = user_config.get("default_backend") or "codex"
        resume_record = _find_last_job_for_backend(store, probe_id)
        if resume_record is None:
            return None, f"delegate: no resumable job found for backend {probe_id!r}"
        return resume_record, None
    return None, None


def _resolve_task_second_opinion(store, args):
    """Resolve --second-opinion/--of into (record, error_message)."""
    if not getattr(args, "second_opinion", False):
        return None, None
    if not getattr(args, "of", None):
        return None, "delegate: --second-opinion requires --of <job-id>"
    of_id, of_error = _resolve_job_id(store, args.of)
    if of_error:
        return None, f"delegate: {of_error}"
    try:
        return store.read(of_id), None
    except (OSError, ValueError) as exc:
        return None, f"delegate: cannot read job {args.of!r}: {exc}"


def _resolve_task_backend_entry(args, backends, user_config, resume_record):
    """Resolve the backend registry entry to dispatch to. Returns (entry, error_message)."""
    if resume_record is not None:
        backend_name = resume_record["backend"]
        if args.backend:
            explicit = registry.resolve_backend(backends, args.backend)
            if explicit is None or explicit["id"] != backend_name:
                return None, (
                    f"delegate: --backend {args.backend!r} does not match resumed job's backend {backend_name!r}"
                )
    else:
        backend_name = args.backend or user_config.get("default_backend") or "codex"

    entry = registry.resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        return None, f"delegate: unknown backend {backend_name!r} (known: {known})"
    return entry, None


def _warn_if_second_opinion_same_backend(
    second_opinion_record, entry, backends, user_config, services_disabled
):
    """Print a warning if the second-opinion backend matches the original job's backend."""
    if (
        second_opinion_record is None
        or second_opinion_record.get("backend") != entry["id"]
    ):
        return
    ready_alternatives = []
    for other in backends:
        if other["id"] == entry["id"]:
            continue
        try:
            row = readiness.probe_backend_readiness(
                other, user_config, services_disabled
            )
        except (OSError, ValueError):
            continue
        if row.get("state") == "ready":
            ready_alternatives.append(other["id"])
    print(
        "delegate: warning: second opinion backend {!r} is the same as the original job's backend"
        " (ready alternatives: {})".format(
            entry["id"], ", ".join(sorted(ready_alternatives)) or "none"
        ),
        file=sys.stderr,
    )


def _check_task_backend_ready(entry, user_config, services_disabled, model_tier):
    """Check backend is enabled and its executable is available. Returns (error_message, exit_code)."""
    enabled, layer = config.effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if not enabled:
        return (
            "delegate: backend {!r} disabled by {} config; run `delegate.py setup` for alternatives".format(
                entry["id"], layer
            ),
            3,
        )
    unavailable = backend._executable_missing(
        backend.build_invoke_argv(
            entry, False, model_tier, {"output_file": "/dev/null"}
        )
    )
    if unavailable:
        return (
            "delegate: backend {!r} unavailable ({}); run `delegate.py setup` to check remediation and alternatives".format(
                entry["id"], unavailable
            ),
            3,
        )
    return None, None


def _build_task_prompt(args, second_opinion_record):
    """Build the effective prompt text and write flag.

    Returns (prompt, write, error_or_None). Never raises: a bad
    --prompt-file must exit 2 through the caller, not traceback.
    """
    if second_opinion_record is not None and getattr(args, "prompt", None) is None:
        # --second-opinion runs with no positional prompt; avoid blocking on
        # sys.stdin.read() (nothing is piped in this mode) and default to "".
        prompt = ""
    else:
        prompt, prompt_error = backend._read_prompt(args)
        if prompt_error:
            return None, False, prompt_error
    if second_opinion_record is None:
        return prompt, bool(args.write), None
    so_prompt = second_opinion_record.get(
        "prompt_summary"
    ) or second_opinion_record.get("job_id")
    so_envelope = second_opinion_record.get("envelope") or {}
    prompt = (
        "Second opinion requested on job {} (backend={}).\n"
        "Original task: {}\n"
        "Prior findings: {}\n\n{}".format(
            second_opinion_record["job_id"],
            second_opinion_record.get("backend"),
            so_prompt,
            json.dumps(so_envelope) if so_envelope else "(none)",
            prompt,
        )
    )
    return prompt, False, None


def _build_task_extra(
    args, entry, resume_record, second_opinion_record, model_tier, budget, write
):
    """Assemble the job-record `extra` dict for cmd_task, warning on unsupported resume."""
    resume_from_session_ref = None
    if resume_record is not None and not getattr(args, "fresh", False):
        if entry.get("resume"):
            resume_from_session_ref = resume_record.get("session_ref")
        else:
            print(
                "delegate: backend {!r} does not support resume; sending context fresh".format(
                    entry["id"]
                ),
                file=sys.stderr,
            )
    extra = {
        "kind": "task",
        "write": write,
        "model": model_tier,
        "budget_seconds": budget,
    }
    if resume_from_session_ref:
        extra["resume_from_session_ref"] = resume_from_session_ref
    if second_opinion_record is not None:
        extra["second_opinion_of"] = second_opinion_record["job_id"]
    return extra


_PROMPT_SUMMARY_MAX_CHARS = 2000


def _dispatch_task(store, args, entry, model_tier, extra, prompt, prompt_bytes):
    """Create the job record and either background-spawn it or run it synchronously."""
    extra = dict(extra)
    extra["prompt_summary"] = prompt[:_PROMPT_SUMMARY_MAX_CHARS]
    record = store.create(entry["id"], extra=extra)
    job_dir = store.job_dir(record["job_id"])
    jobstore._write_0600(os.path.join(job_dir, "prompt.txt"), prompt)

    print(
        "delegate: dispatching to backend {!r} (model={})".format(
            entry["id"], model_tier
        ),
        file=sys.stderr,
    )

    if args.background:
        worker._spawn_worker(store, record["job_id"])
        if args.json:
            print(
                json.dumps(
                    {
                        "job_id": record["job_id"],
                        "backend": entry["id"],
                        "state": "queued",
                    }
                )
            )
        else:
            print("job_id: {}".format(record["job_id"]))
            print("check: delegate.py status {}".format(record["job_id"]))
        return 0

    store.mutate(record["job_id"], lambda rec: dict(rec, state="running"))
    final = worker._run_backend_foreground(
        store, record["job_id"], entry, record, prompt_bytes
    )
    envelope = final.get("envelope") or {}
    envelope.setdefault("job_id", record["job_id"])

    if args.json:
        print(json.dumps(envelope))
    else:
        print("job_id: {}".format(record["job_id"]))
        print("backend: {}".format(entry["id"]))
        if extra.get("second_opinion_of"):
            print("second_opinion_of: {}".format(extra["second_opinion_of"]))
        print("outcome: {}".format(envelope.get("outcome")))
        if envelope.get("error"):
            print("error: {}".format(envelope["error"]))

    if final.get("state") == "timeout":
        return 1
    return 0 if envelope.get("outcome") != "failure" else 1


def cmd_task(args, backends, user_config, services_disabled):
    store = jobstore.JobStore()
    resume_record, resume_error = _resolve_task_resume(
        store, args, backends, user_config
    )
    if resume_error:
        print(resume_error, file=sys.stderr)
        return 2

    second_opinion_record, so_error = _resolve_task_second_opinion(store, args)
    if so_error:
        print(so_error, file=sys.stderr)
        return 2

    entry, backend_error = _resolve_task_backend_entry(
        args, backends, user_config, resume_record
    )
    if backend_error:
        print(backend_error, file=sys.stderr)
        return 2

    _warn_if_second_opinion_same_backend(
        second_opinion_record, entry, backends, user_config, services_disabled
    )

    prompt, write, prompt_error = _build_task_prompt(args, second_opinion_record)
    if prompt_error:
        print(prompt_error, file=sys.stderr)
        return 2

    model_tier = backend.resolve_model_tier(entry, user_config, args.model)
    ready_error, ready_code = _check_task_backend_ready(
        entry, user_config, services_disabled, model_tier
    )
    if ready_error:
        print(ready_error, file=sys.stderr)
        return ready_code

    prompt_bytes = prompt.encode("utf-8")
    limit_error = backend.check_payload_limits(entry, prompt_bytes)
    if limit_error:
        print(f"delegate: {limit_error}", file=sys.stderr)
        return 2

    budget = backend.resolve_budget(entry, user_config, args.budget)
    extra = _build_task_extra(
        args, entry, resume_record, second_opinion_record, model_tier, budget, write
    )
    return _dispatch_task(store, args, entry, model_tier, extra, prompt, prompt_bytes)
