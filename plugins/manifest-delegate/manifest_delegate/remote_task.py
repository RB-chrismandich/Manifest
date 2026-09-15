"""Submit cloud tasks with durable intent and no implicit retry or resume."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from . import backend, config, jules_cli
from .jobstore_files import _atomic_write_0600, _fsync_directory


def is_remote(entry: dict) -> bool:
    """Select the explicit remote-session execution contract."""
    return (entry.get("execution") or {}).get("kind") == "remote_session"


def validate_request(args, entry: dict, user_config: dict) -> str | None:
    """Reject local-only capabilities before any cloud submission."""
    if not getattr(args, "remote_write", False) or getattr(
        args, "second_opinion", False
    ):
        return "remote tasks require --remote-write; read-only work is unsupported"
    if getattr(args, "write", False):
        return "use --remote-write for cloud execution; --write scopes local edits"
    for option in (
        "resume",
        "resume_last",
        "model_chain",
        "model_fallback",
        "skill_path",
        "replacement_tier",
        "replacement_mode",
        "fallback_decision",
    ):
        if getattr(args, option, None):
            return f"remote backend does not support --{option.replace('_', '-')}"
    model = getattr(args, "model", None) or (
        user_config.get("backends", {}).get(entry["id"], {}).get("model")
    )
    if model not in (None, "auto"):
        return "remote backend chooses its model; only auto is supported"
    repo = getattr(args, "repo", None)
    if not isinstance(repo, str) or not jules_cli.REPOSITORY.fullmatch(repo):
        return "remote task requires --repo OWNER/REPO (GitHub)"
    if getattr(args, "remote_base", None) != "provider-selected":
        return (
            "Jules CLI cannot pin a branch; acknowledge --remote-base provider-selected"
        )
    return None


def submit(store, backend_id: str, repo: str, payload: bytes, budget: int) -> dict:
    """Persist uncertainty before spawning; a crash can never imply safe retry."""
    record = store.create(
        backend_id,
        {
            "kind": "task",
            "execution_kind": "remote_session",
            "state": "remote_submission_unknown",
            "model": "auto",
            "remote": {
                "driver": "jules_cli",
                "repository": repo,
                "base": "provider-selected",
                "session_id": None,
                "url": None,
            },
        },
    )
    # create() closes files but does not fsync. Flush intent and directory
    # entries before the remote call, including a power-loss crash window.
    _atomic_write_0600(
        os.path.join(store.job_dir(record["job_id"]), "record.json"),
        json.dumps(record, indent=2),
    )
    _fsync_directory(store.job_dir(record["job_id"]))
    _fsync_directory(store.workspace_dir)
    try:
        result = jules_cli.run(
            ["jules", "remote", "new", "--repo", repo], payload=payload, timeout=budget
        )
        session_id = jules_cli.parse_session_id(result.stdout)
        error = (
            None
            if session_id
            else "submission unverified; inspect Jules before submitting again"
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        session_id = None
        error = f"submission unverified ({type(exc).__name__}); inspect Jules before submitting again"

    def publish(current):
        if session_id:
            current["remote"].update(
                session_id=session_id,
                url=f"https://jules.google.com/session/{session_id}",
            )
            current["state"] = "remote_pending"
        else:
            current["error"] = error
        return current

    return store.mutate(record["job_id"], publish)


def cmd_task(
    store, args, entry: dict, user_config: dict, services_disabled: set
) -> int:
    """Dispatch one remote task after checking capabilities and repository access."""
    error = validate_request(args, entry, user_config)
    enabled, layer = config.effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if error or not enabled:
        print(f"delegate: {error or f'backend disabled by {layer}'}", file=sys.stderr)
        return 2
    prompt, error = backend._read_prompt(args)
    if error or not prompt or not prompt.strip():
        print(
            error or "delegate: remote task requires a non-empty prompt",
            file=sys.stderr,
        )
        return 2
    payload = prompt.encode("utf-8")
    error = backend.check_payload_limits(entry, payload)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2
    canonical_repo = jules_cli.normalize_github_repo(args.repo)
    try:
        probe = jules_cli.run(["jules", "remote", "list", "--repo"])
        accessible = {
            jules_cli.normalize_github_repo(row)
            for row in jules_cli.parse_repositories(probe.stdout + probe.stderr)
        }
        if probe.returncode or canonical_repo not in accessible:
            raise ValueError(
                "repository access unverified; run jules login and check GitHub App access"
            )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"delegate: {exc}", file=sys.stderr)
        return 1
    budget = min(backend.resolve_budget(entry, user_config, args.budget), 120)
    record = submit(store, entry["id"], canonical_repo, payload, budget)
    from .remote_jobs import render

    render(record, args.json)
    return 0 if record["state"] == "remote_pending" else 1
