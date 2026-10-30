"""manifest-delegate: review."""

import json
import os
import sys
import time

from . import backend, jobstore, registry, review_git, task, worker
from . import envelope as envelope_mod
from .review_git import ReviewDiffError

MAX_UNTRACKED_FILES = 128

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

_REVIEW_OUTPUT_CONTRACT = (
    "\n\nDo not create artifacts, plans, files, or ask for approval. This is a "
    "single-turn read-only review; inspect the diff and return the final verdict now. "
    "End your final message with exactly one fenced JSON block "
    "(```json ... ```), and nothing after it, matching this shape:\n"
    "```json\n"
    "{\n"
    '  "backend": "<your backend id>",\n'
    '  "model": "<model or null>",\n'
    '  "outcome": "success",\n'
    '  "attempted": "<what you reviewed>",\n'
    '  "changes": [],\n'
    '  "succeeded": [],\n'
    '  "failed": [],\n'
    '  "follow_ups": [],\n'
    '  "findings": [{"severity": "critical|high|medium|low|info", "text": "<finding>"}]\n'
    "}\n"
    "```\n"
    'Set "findings" to [] when the diff has no issues. '
    "Every array field must be an array of strings.\n"
    + envelope_mod.REVIEW_OUTCOME_SEMANTICS
    + "\n"
)


def _run_git(args_list, cwd, *, max_bytes=backend.TASK_LIMIT, deadline=None):
    """Run bounded Git, accepting exit 1 for no-index differences."""
    proc = review_git.capture_git(
        args_list, cwd, max_bytes=max_bytes, deadline=deadline
    )
    if proc.returncode not in (0, 1):
        raise ReviewDiffError(
            f"git {' '.join(args_list)} failed (exit {proc.returncode}): "
            f"{(proc.stderr or '').strip()[:300]}"
        )
    return proc.stdout


def _untracked_diff(cwd, *, max_bytes=backend.TASK_LIMIT, deadline=None):
    """Include every untracked file within the remaining diff and work budgets."""
    deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + review_git.GIT_TIMEOUT_SECONDS
    )
    listing = _run_git(
        ["ls-files", "--others", "--exclude-standard", "-z"], cwd, deadline=deadline
    )
    if listing.count("\0") > MAX_UNTRACKED_FILES:
        raise ReviewDiffError(
            f"untracked file count limit exceeded ({MAX_UNTRACKED_FILES})"
        )
    paths = [path for path in listing.split("\0") if path]
    parts = []
    for path in paths:
        numstat = _run_git(
            ["diff", "--no-index", "--numstat", "--", "/dev/null", path],
            cwd,
            max_bytes=65536,
            deadline=deadline,
        )
        if numstat.strip().startswith("-\t-\t"):
            part = f"Binary file {path} (untracked)\n"
        else:
            part = _run_git(
                ["diff", "--no-index", "--", "/dev/null", path],
                cwd,
                max_bytes=max_bytes,
                deadline=deadline,
            )
        max_bytes -= len(part.encode("utf-8"))
        if max_bytes < 0:
            raise ReviewDiffError("git review diff byte limit exceeded")
        parts.append(part)
    return "".join(parts)


def _scope_diff(diff_args, cwd, *, deadline=None):
    deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + review_git.GIT_TIMEOUT_SECONDS
    )
    tracked = _run_git(["diff", *diff_args], cwd, deadline=deadline)
    return tracked + _untracked_diff(
        cwd,
        max_bytes=backend.TASK_LIMIT - len(tracked.encode("utf-8")),
        deadline=deadline,
    )


# Candidate refs to merge-base HEAD against when no explicit --base is given,
# most-specific first: the branch's own upstream, then the repo's default branch.
_BRANCH_BASE_CANDIDATES = (
    "@{upstream}",
    "origin/HEAD",
    "origin/main",
    "origin/master",
    "main",
    "master",
)


def _git_or_none(args_list, cwd, *, deadline=None):
    """Missing refs return None; incomplete or oversized observations fail closed."""
    proc = review_git.capture_git(args_list, cwd, max_bytes=4096, deadline=deadline)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _resolve_branch_base(base, cwd, *, deadline=None):
    """Resolve the base ref for a branch-scope diff.

    An explicit --base wins. Otherwise merge-base HEAD against the branch's
    upstream, then the repository's default branch. Fails VISIBLY
    (ReviewDiffError) rather than defaulting to HEAD~1 — a branch review that
    silently diffs only the latest commit excludes every earlier commit on the
    branch and reports success, a false-green.
    """
    if base:
        return base
    for ref in _BRANCH_BASE_CANDIDATES:
        merge_base = _git_or_none(["merge-base", "HEAD", ref], cwd, deadline=deadline)
        if merge_base:
            return merge_base
    raise ReviewDiffError(
        "branch review needs a base but none could be resolved (no upstream, "
        "and no origin/HEAD, origin/main, origin/master, main, or master to "
        "merge-base against). Pass --base <ref> explicitly."
    )


def assemble_review_diff(scope, base, cwd=None):
    """Build the review/gate diff: tracked+staged+untracked, fail closed visibly.

    Raises ReviewDiffError (developer-visible) instead of silently returning
    an empty diff when any underlying git invocation fails.
    Collection permits at most 1 MiB of diff, 128 untracked files, and 30 seconds;
    each Git stderr stream is limited to 64 KiB. No partial diff is returned.
    """
    deadline = time.monotonic() + review_git.GIT_TIMEOUT_SECONDS
    if scope == "working-tree":
        return _scope_diff(["HEAD"], cwd, deadline=deadline)
    if scope == "branch":
        ref = _resolve_branch_base(base, cwd, deadline=deadline)
        return _scope_diff([f"{ref}...HEAD"], cwd, deadline=deadline)
    # auto: prefer working-tree changes; fall back to the full branch diff.
    diff = _scope_diff(["HEAD"], cwd, deadline=deadline)
    if diff.strip():
        return diff
    ref = _resolve_branch_base(base, cwd, deadline=deadline)
    return _scope_diff([f"{ref}...HEAD"], cwd, deadline=deadline)


def _build_review_prompt(args):
    """Build the review prompt (adversarial or standard) from the current diff."""
    diff = assemble_review_diff(args.scope, args.base, cwd=os.getcwd())
    if getattr(args, "adversarial", None) is not None:
        focus = " ".join(args.adversarial).strip()
        return (
            "Adversarial review: challenge the design of the following change.\n"
            "Focus: {}".format(focus or "(none specified)")
            + _REVIEW_OUTPUT_CONTRACT
            + diff
        )
    return (
        "Review the following change for correctness, safety, and quality."
        + _REVIEW_OUTPUT_CONTRACT
        + diff
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
    # A non-failure review that OMITS findings is an incomplete result, not a
    # clean pass — mirror the Stop gate: convert it to a failure so `review`
    # never reports success on a backend that never supplied a review result.
    if final.get("state") != "timeout" and envelope.get("outcome") != "failure":
        _, error_reason = envelope_mod.validate_findings(envelope, label="review")
        if error_reason:
            envelope = dict(envelope, outcome="failure", error=error_reason)
    _print_review_envelope(args, entry, envelope)

    if final.get("state") == "timeout":
        return 1
    # Only `success` is a clean exit 0. `partial` means the reviewer could not
    # inspect the whole diff — reporting it as a clean review would be a
    # false-green, so it exits nonzero like `failure` (mirrors the Stop gate).
    return 0 if envelope.get("outcome") == "success" else 1


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

    if (entry.get("execution") or {}).get("read_only") is False:
        print("delegate: backend does not support read-only reviews", file=sys.stderr)
        return 2

    model_tier = backend.resolve_model_tier(entry, user_config, args.model)
    ready_error, ready_code = task._check_task_backend_ready(
        entry, user_config, services_disabled, model_tier
    )
    if ready_error:
        print(ready_error, file=sys.stderr)
        return ready_code

    try:
        prompt = _build_review_prompt(args)
    except ReviewDiffError as exc:
        print(f"delegate: {exc}", file=sys.stderr)
        return 2
    prompt_bytes = prompt.encode("utf-8")
    limit_error = backend.check_payload_limits(entry, prompt_bytes)
    if limit_error:
        print(f"delegate: {limit_error}", file=sys.stderr)
        return 2

    budget = backend.resolve_budget(entry, user_config, args.budget)
    return _dispatch_review(
        store, args, entry, model_tier, budget, prompt, prompt_bytes
    )
