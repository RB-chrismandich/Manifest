"""Observe remote work independently of local process ownership."""

import json
import subprocess
import sys
import time
from pathlib import Path

from . import jobstore, jules_cli


def render(record: dict, json_mode: bool) -> None:
    """Report cloud state and its reference without fabricating a result envelope."""
    if json_mode:
        print(json.dumps(record))
        return
    print(f"job_id: {record['job_id']}\nstate: {record['state']}")
    remote = record.get("remote") or {}
    if remote.get("url"):
        print(f"session: {remote['url']}")
    for key in ("error", "status_error", "artifact_path", "applied_at"):
        if record.get(key):
            print(f"{key}: {record[key]}")


def refresh(store, record: dict, *, timeout: float = 30) -> dict:
    """One bounded read-only poll; missing/unknown rows preserve the cloud state."""
    remote = record.get("remote") or {}
    session_id = remote.get("session_id")
    if not isinstance(session_id, str) or not jules_cli.SESSION.fullmatch(session_id):
        return record
    if record["state"] in {"completed", "failed"}:
        return record
    state = None
    try:
        response = jules_cli.run(
            ["jules", "remote", "list", "--session"], timeout=timeout
        )
        if response.returncode == 0 and not jules_cli.auth_error(
            response.stdout + response.stderr
        ):
            state = jules_cli.parse_session_state(response.stdout, session_id)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # A failed observation says nothing about the cloud task's lifetime.
        state = None

    def publish(current):
        if current["version"] != record["version"]:
            # A concurrent observer already published a newer observation.
            return None
        if state:
            current["state"] = state
            current.pop("status_error", None)
        else:
            current["status_error"] = (
                "remote status unavailable; inspect the session URL"
            )
        current["remote_checked_at"] = time.time()
        return current

    return store.mutate(record["job_id"], publish)


def status(store, args, record: dict) -> int:
    """Wait only for known pending work; observation failure returns promptly."""
    duration = args.timeout if args.timeout is not None else 600
    if duration <= 0:
        print("delegate: --timeout must be positive", file=sys.stderr)
        return 2
    deadline = time.monotonic() + duration
    while True:
        record = refresh(
            store, record, timeout=max(0.1, min(30, deadline - time.monotonic()))
        )
        if (
            not args.wait
            or record["state"] != "remote_pending"
            or record.get("status_error")
            or time.monotonic() >= deadline
        ):
            break
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    render(record, args.json)
    return (
        1
        if record.get("status_error") or record["state"] == "remote_submission_unknown"
        else 0
    )


def _resolve(args, verb):
    from .task_resolution import _resolve_job_id_anywhere

    store = jobstore.JobStore()
    if not isinstance(getattr(args, "job_id", None), str) or not args.job_id:
        raise ValueError("job id or prefix required")
    store, resolved, error = _resolve_job_id_anywhere(store, args.job_id)
    if error:
        raise ValueError(error)
    record = store.read(resolved)
    if record.get("execution_kind") != "remote_session":
        raise ValueError(f"{verb} requires a remote-session job")
    remote = record.get("remote") or {}
    if remote.get("driver") != "jules_cli" or not jules_cli.SESSION.fullmatch(
        remote.get("session_id") or ""
    ):
        raise ValueError("remote session reference is unverified")
    return store, record


def cmd_pull(args) -> int:
    """Fetch the completed diff into job storage; applying is a separate explicit action."""
    try:
        store, record = _resolve(args, "pull")
        record = refresh(store, record)
        if record["state"] != "completed":
            raise ValueError(
                "remote completion is unverified; inspect the session before pulling"
            )
        response = jules_cli.run(
            ["jules", "remote", "pull", "--session", record["remote"]["session_id"]],
            cwd=store.job_dir(record["job_id"]),
        )
        if response.returncode or not response.stdout.startswith("diff --git "):
            raise ValueError(
                "Jules did not return a recognizable patch; nothing applied"
            )
        # Store the exact bytes we inspect. git apply does boundary checks when
        # explicitly requested; never ask the provider to apply unseen output.
        store.replace_owned_file(record["job_id"], "changes.patch", response.stdout)
        path = str(Path(store.job_dir(record["job_id"])) / "changes.patch")
        # Completion records stay immutable. The artifact is a separate owned
        # file; report its derived path without reopening terminal state.
        render(dict(record, artifact_path=path), args.json)
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"delegate: {exc}", file=sys.stderr)
        return 1


def cmd_apply(args) -> int:
    """Apply only the previously fetched artifact to the exact recorded repository."""
    try:
        store, record = _resolve(args, "apply")
        path = Path(store.job_dir(record["job_id"])) / "changes.patch"
        if record["state"] != "completed" or path.is_symlink() or not path.is_file():
            raise ValueError(
                "fetch and review the patch with delegate.py pull JOB_ID first"
            )
        root_result = jules_cli.run(["git", "rev-parse", "--show-toplevel"])
        root_text = root_result.stdout.strip()
        root = Path(root_text)
        if (
            root_result.returncode
            or not root_text
            or not root.is_absolute()
            or not root.is_dir()
        ):
            raise ValueError("could not resolve the current repository root")
        root_cwd = str(root.resolve())
        origin = jules_cli.run(["git", "remote", "get-url", "origin"], cwd=root_cwd)
        recorded_repo = jules_cli.normalize_github_repo(record["remote"]["repository"])
        origin_repo = (
            jules_cli.normalize_github_repo(origin.stdout.strip())
            if origin.returncode == 0
            else None
        )
        if origin.returncode or recorded_repo is None or origin_repo != recorded_repo:
            raise ValueError("current repository does not match the remote job")
        clean = jules_cli.run(["git", "status", "--porcelain"], cwd=root_cwd)
        if clean.returncode or clean.stdout.strip():
            raise ValueError("apply requires a clean working tree")
        for command in (
            ["git", "apply", "--check", "--", str(path)],
            ["git", "apply", "--", str(path)],
        ):
            result = jules_cli.run(command, cwd=root_cwd)
            if result.returncode:
                raise ValueError(
                    "patch did not apply cleanly; inspect the saved artifact"
                )
        render(dict(record, artifact_path=str(path), applied_at=time.time()), args.json)
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"delegate: {exc}", file=sys.stderr)
        return 1
