"""manifest-delegate: review."""

import json
import os
import subprocess
import sys

from . import backend, jobstore, registry, task, worker

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class ReviewDiffError(Exception):
    """Raised when git invocations backing a review diff fail visibly."""


def _run_git(args_list, cwd):
    """Run git, treating exit codes 0/1 as success (1 = "differs", not error)."""
    try:
        proc = subprocess.run(
            ["git", *args_list], capture_output=True, text=True, cwd=cwd
        )
    except OSError as exc:
        raise ReviewDiffError(
            "git {} failed to launch: {}".format(" ".join(args_list), exc)
        ) from exc
    if proc.returncode not in (0, 1):
        raise ReviewDiffError(
            f"git {' '.join(args_list)} failed (exit {proc.returncode}): "
            f"{(proc.stderr or '').strip()[:300]}"
        )
    return proc.stdout or ""


def _untracked_diff(cwd):
    """Synthesize diff text for untracked files (git diff HEAD omits these)."""
    listing = _run_git(["ls-files", "--others", "--exclude-standard"], cwd)
    parts = []
    for path in filter(None, listing.splitlines()):
        numstat = _run_git(
            ["diff", "--no-index", "--numstat", "--", "/dev/null", path], cwd
        )
        if numstat.strip().startswith("-\t-\t"):
            parts.append(f"Binary file {path} (untracked)\n")
            continue
        parts.append(_run_git(["diff", "--no-index", "--", "/dev/null", path], cwd))
    return "".join(parts)


def _scope_diff(diff_args, cwd):
    return _run_git(["diff", *diff_args], cwd) + _untracked_diff(cwd)


def assemble_review_diff(scope, base, cwd=None):
    """Build the review/gate diff: tracked+staged+untracked, fail open visibly.

    Raises ReviewDiffError (developer-visible) instead of silently returning
    an empty diff when any underlying git invocation fails.
    """
    if scope == "working-tree":
        return _scope_diff(["HEAD"], cwd)
    if scope == "branch":
        ref = base or "HEAD~1"
        return _scope_diff([f"{ref}...HEAD"], cwd)
    # auto: prefer working-tree changes; fall back to branch diff against base.
    diff = _scope_diff(["HEAD"], cwd)
    if diff.strip():
        return diff
    ref = base or "HEAD~1"
    return _scope_diff([f"{ref}...HEAD"], cwd)


def _build_review_prompt(args):
    """Build the review prompt (adversarial or standard) from the current diff."""
    diff = assemble_review_diff(args.scope, args.base, cwd=os.getcwd())
    if getattr(args, "adversarial", None) is not None:
        focus = " ".join(args.adversarial).strip()
        return (
            "Adversarial review: challenge the design of the following change.\n"
            "Focus: {}\n\n{}".format(focus or "(none specified)", diff)
        )
    return (
        f"Review the following change for correctness, safety, and quality.\n\n{diff}"
    )


def _dispatch_review(store, args, entry, model_tier, budget, prompt, prompt_bytes):
    """Create the review job record and either background-spawn it or run it synchronously."""
    extra = {
        "kind": "review",
        "write": False,
        "model": model_tier,
        "budget_seconds": budget,
    }
    record = store.create(entry["id"], extra=extra)
    job_dir = store.job_dir(record["job_id"])
    jobstore._write_0600(os.path.join(job_dir, "prompt.txt"), prompt)

    print(
        "delegate: dispatching review to backend {!r} (model={})".format(
            entry["id"], model_tier
        ),
        file=sys.stderr,
    )

    if args.background:
        return _dispatch_review_background(store, args, entry, record)

    store.mutate(record["job_id"], lambda rec: dict(rec, state="running"))
    final = worker._run_backend_foreground(
        store, record["job_id"], entry, record, prompt_bytes
    )
    envelope = _severity_sorted(final.get("envelope") or {})
    _print_review_envelope(args, entry, envelope)

    if final.get("state") == "timeout":
        return 1
    return 0 if envelope.get("outcome") != "failure" else 1


def _dispatch_review_background(store, args, entry, record):
    """Spawn the review worker and report the job handle."""
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


def _severity_sorted(envelope):
    """Order `findings` most-severe first, in place. Unknown severities sort last."""
    findings = envelope.get("findings")
    if isinstance(findings, list):
        envelope["findings"] = sorted(
            findings,
            key=lambda f: _SEVERITY_RANK.get(
                (f or {}).get("severity"), len(_SEVERITY_RANK)
            ),
        )
    return envelope


def _print_review_envelope(args, entry, envelope):
    """Render a finished review as JSON or as severity-ordered plain text."""
    if args.json:
        print(json.dumps(envelope))
        return
    print("backend: {}".format(entry["id"]))
    print("outcome: {}".format(envelope.get("outcome")))
    for finding in envelope.get("findings") or []:
        print("[{}] {}".format(finding.get("severity", "?"), finding.get("text", "")))
    if envelope.get("error"):
        print("error: {}".format(envelope["error"]))


def cmd_review(args, backends, user_config, services_disabled):
    store = jobstore.JobStore()
    backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = registry.resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        print(
            f"delegate: unknown backend {backend_name!r} (known: {known})",
            file=sys.stderr,
        )
        return 2

    model_tier = backend.resolve_model_tier(entry, user_config, args.model)
    ready_error, ready_code = task._check_task_backend_ready(
        entry, user_config, services_disabled, model_tier
    )
    if ready_error:
        print(ready_error, file=sys.stderr)
        return ready_code

    prompt = _build_review_prompt(args)
    prompt_bytes = prompt.encode("utf-8")
    limit_error = backend.check_payload_limits(entry, prompt_bytes)
    if limit_error:
        print(f"delegate: {limit_error}", file=sys.stderr)
        return 2

    budget = backend.resolve_budget(entry, user_config, args.budget)
    return _dispatch_review(
        store, args, entry, model_tier, budget, prompt, prompt_bytes
    )
