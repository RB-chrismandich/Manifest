"""Job, backend, and second-opinion resolution for delegate tasks."""

import hashlib
import json
import sys

from . import backend, config, jobstore, readiness, registry

_SECOND_OPINION_MAX_FINDINGS = 32
_SECOND_OPINION_MAX_TITLE_BYTES = 512
_SECOND_OPINION_MAX_DETAIL_BYTES = 4096
_SECOND_OPINION_MAX_TEXT_BYTES = (
    _SECOND_OPINION_MAX_TITLE_BYTES + _SECOND_OPINION_MAX_DETAIL_BYTES + 2
)
_SECOND_OPINION_MAX_TOTAL_BYTES = 65_536


def _resolve_job_id(store, prefix):
    ids = store.list_job_ids()
    if prefix in ids:
        return prefix, None
    matches = sorted(job_id for job_id in ids if job_id.startswith(prefix))
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"no job matches {prefix!r}"
    return None, "ambiguous job id {!r} matches: {}".format(prefix, ", ".join(matches))


def _resolve_sole_active(store):
    active = []
    for job_id in store.list_job_ids():
        try:
            record = store.reap_if_dead(job_id)
        except (OSError, ValueError):
            continue
        if record.get("state") in jobstore.NON_TERMINAL_STATES:
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
            record = store.read(job_id)
        except (OSError, ValueError):
            continue
        if record.get("backend") == backend_id and record.get("session_ref"):
            candidates.append(record)
    if not candidates:
        return None
    candidates.sort(key=lambda record: record.get("updated_at", 0))
    return candidates[-1]


def _resolve_task_resume(store, args, backends, user_config):
    """Resolve --resume / --resume-last into a record or error."""
    if getattr(args, "resume", None):
        job_id, resume_error = _resolve_job_id(store, args.resume)
        if not job_id:
            return None, resume_error
        try:
            return store.read(job_id), None
        except (OSError, ValueError) as error:
            return None, f"delegate: cannot read job {args.resume!r}: {error}"
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


def _validate_finding(finding):
    if not isinstance(finding, dict):
        raise ValueError("second-opinion findings have an invalid schema")
    if set(finding) == {"text", "severity"}:
        text = finding["text"]
        severity = finding["severity"]
    elif set(finding) == {"title", "detail", "severity"}:
        title = finding["title"]
        detail = finding["detail"]
        severity = finding["severity"]
        if not all(
            isinstance(value, str) and value for value in (title, detail, severity)
        ):
            raise ValueError("second-opinion findings must contain non-empty text")
        if len(title.encode("utf-8")) > _SECOND_OPINION_MAX_TITLE_BYTES:
            raise ValueError("second-opinion finding title is too large")
        if len(detail.encode("utf-8")) > _SECOND_OPINION_MAX_DETAIL_BYTES:
            raise ValueError("second-opinion finding detail is too large")
        text = f"{title}: {detail}"
    else:
        raise ValueError("second-opinion findings have an invalid schema")
    if not all(isinstance(value, str) and value for value in (text, severity)):
        raise ValueError("second-opinion findings must contain non-empty text")
    if len(text.encode("utf-8")) > _SECOND_OPINION_MAX_TEXT_BYTES:
        raise ValueError("second-opinion finding text is too large")
    if len(severity.encode("utf-8")) > 32:
        raise ValueError("second-opinion finding severity is too large")
    return {"severity": severity, "text": text}


def _validated_second_opinion_context(record):
    if record.get("state") not in jobstore.TERMINAL_STATES:
        raise ValueError("second-opinion source job is not terminal")
    attempt_id = record.get("attempt_id")
    if (
        not isinstance(attempt_id, str)
        or not attempt_id
        or record.get("result_attempt_id") != attempt_id
        or record.get("findings_attempt_id") != attempt_id
    ):
        raise ValueError("second-opinion findings do not belong to one current attempt")
    envelope = record.get("envelope")
    findings = envelope.get("findings") if isinstance(envelope, dict) else None
    if not isinstance(findings, list) or not findings:
        raise ValueError("second-opinion source has no valid findings")
    if len(findings) > _SECOND_OPINION_MAX_FINDINGS:
        raise ValueError("second-opinion findings exceed the bounded count")
    normalized = [_validate_finding(finding) for finding in findings]
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) > _SECOND_OPINION_MAX_TOTAL_BYTES:
        raise ValueError("second-opinion findings exceed the bounded total")
    return {
        "job_id": record["job_id"],
        "backend": record.get("backend"),
        "version": record["version"],
        "attempt_id": attempt_id,
        "findings": normalized,
        "findings_digest": hashlib.sha256(encoded).hexdigest(),
    }


def _resolve_task_second_opinion(store, args):
    """Resolve --second-opinion/--of into a record or error."""
    if not getattr(args, "second_opinion", False):
        return None, None
    if not getattr(args, "of", None):
        return None, "delegate: --second-opinion requires --of <job-id>"
    source_id, source_error = _resolve_job_id(store, args.of)
    if source_error:
        return None, f"delegate: {source_error}"
    try:
        return _validated_second_opinion_context(store.read_locked(source_id)), None
    except (OSError, ValueError) as error:
        return None, f"delegate: cannot read job {args.of!r}: {error}"


def _resolve_task_backend_entry(args, backends, user_config, resume_record):
    """Resolve the backend registry entry to dispatch to."""
    if resume_record is not None:
        backend_name = resume_record["backend"]
        if args.backend:
            explicit = registry.resolve_backend(backends, args.backend)
            if explicit is None or explicit["id"] != backend_name:
                return None, (
                    f"delegate: --backend {args.backend!r} does not match resumed "
                    f"job's backend {backend_name!r}"
                )
    else:
        backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = registry.resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(item["id"] for item in backends))
        return None, f"delegate: unknown backend {backend_name!r} (known: {known})"
    return entry, None


def _warn_if_second_opinion_same_backend(
    second_opinion_record, entry, backends, user_config, services_disabled
):
    """Warn when a ready alternative could provide more independent review."""
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
        "delegate: warning: second opinion backend {!r} is the same as the "
        "original job's backend (ready alternatives: {})".format(
            entry["id"], ", ".join(sorted(ready_alternatives)) or "none"
        ),
        file=sys.stderr,
    )


def _check_task_backend_ready(entry, user_config, services_disabled, model_tier):
    """Return an error and exit code unless the backend is dispatch-ready."""
    enabled, layer = config.effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if not enabled:
        return (
            "delegate: backend {!r} disabled by {} config; run `delegate.py "
            "setup` for alternatives".format(entry["id"], layer),
            3,
        )
    unavailable = backend._executable_missing(
        backend.build_invoke_argv(
            entry, False, model_tier, {"output_file": "/dev/null"}
        )
    )
    if unavailable:
        return (
            "delegate: backend {!r} unavailable ({}); run `delegate.py setup` "
            "to check remediation and alternatives".format(entry["id"], unavailable),
            3,
        )
    return None, None
