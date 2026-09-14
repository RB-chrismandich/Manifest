"""CLI adapter for the session continuity runtime."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from session_continuity import (
    CheckpointValidationError,
    HandoffDecision,
    PersistenceError,
    SessionContinuityError,
    SessionContinuityStore,
    SessionStatus,
    revalidate_continuation,
    write_checkpoint,
)

_KNOWN_BOUNDARIES = ("active", "safe", "unknown")


def _status_document(status: SessionStatus) -> dict[str, object]:
    return {
        "telemetry": status.telemetry,
        "compaction_count": status.compaction_count,
        "excluded": status.excluded,
    }


def _decision_document(decision: HandoffDecision) -> dict[str, object]:
    return {
        "recommend_fresh_session": decision.recommend_fresh_session,
        "reason": decision.reason,
        "checkpoint_path": (
            str(decision.checkpoint_path) if decision.checkpoint_path else None
        ),
        "continuation_goal": decision.continuation_goal,
    }


def _load_input(path: str) -> object:
    try:
        if path == "-":
            return json.load(sys.stdin)
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PersistenceError(f"unable to load checkpoint input: {error}") from error


def _report_hook_failure(error: BaseException) -> int:
    # Hook delivery must not break compaction. Telemetry becomes unavailable,
    # and the diagnostic keeps the persistence failure visible without payloads.
    print(f"session-continuity: {error}", file=sys.stderr)
    return 0


def _hook_event(harness: str) -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
        if harness == "claude":
            SessionContinuityStore().record_claude_event(event)
    except (OSError, ValueError, SessionContinuityError) as error:
        return _report_hook_failure(error)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    hook = subparsers.add_parser("hook-event", help="record a native lifecycle event")
    hook.add_argument("--harness", required=True)
    status = subparsers.add_parser("status", help="show session telemetry")
    status.add_argument("--session-id", required=True)
    status.add_argument("--harness", required=True)
    defer = subparsers.add_parser(
        "defer", help="suppress handoff reminders for a session"
    )
    defer.add_argument("--session-id", required=True)
    checkpoint = subparsers.add_parser(
        "checkpoint", help="write an integrity-checked checkpoint"
    )
    checkpoint.add_argument("--input", required=True, help="JSON file, or - for stdin")
    recommend = subparsers.add_parser(
        "recommend", help="evaluate the advisory handoff policy"
    )
    recommend.add_argument("--session-id", required=True)
    recommend.add_argument("--boundary", choices=_KNOWN_BOUNDARIES, required=True)
    recommend.add_argument("--checkpoint", type=Path, required=True)
    verify = subparsers.add_parser(
        "verify", help="verify integrity and revalidate continuation authority"
    )
    verify.add_argument("--checkpoint", type=Path, required=True)
    verify.add_argument("--repository-json", required=True)
    verify.add_argument("--operations-json", required=True)
    return parser


def _status(
    args: argparse.Namespace, store: SessionContinuityStore
) -> dict[str, object]:
    return _status_document(store.status(args.session_id, args.harness))


def _defer(
    args: argparse.Namespace, store: SessionContinuityStore
) -> dict[str, object]:
    store.defer(args.session_id)
    return {"session_id": args.session_id, "deferred": True}


def _checkpoint(
    args: argparse.Namespace, _store: SessionContinuityStore
) -> dict[str, object]:
    checkpoint = _load_input(args.input)
    if not isinstance(checkpoint, dict):
        raise CheckpointValidationError("checkpoint input must be a JSON object")
    path = write_checkpoint(checkpoint)
    return {"checkpoint_path": str(path)}


def _recommend(
    args: argparse.Namespace, store: SessionContinuityStore
) -> dict[str, object]:
    return _decision_document(
        store.handoff_decision(args.session_id, args.boundary, args.checkpoint)
    )


def _verify(
    args: argparse.Namespace, _store: SessionContinuityStore
) -> dict[str, object]:
    repository = json.loads(args.repository_json)
    operations = json.loads(args.operations_json)
    if not isinstance(repository, dict) or not isinstance(operations, list):
        raise CheckpointValidationError(
            "repository must be an object and operations must be a list"
        )
    report = revalidate_continuation(args.checkpoint, repository, operations)
    return {
        "trusted": report.trusted,
        "git_changes": list(report.git_changes),
        "ownership_changes": list(report.ownership_changes),
        "continuation_goal": report.continuation_goal,
    }


_COMMANDS: dict[
    str, Callable[[argparse.Namespace, SessionContinuityStore], dict[str, object]]
] = {
    "status": _status,
    "defer": _defer,
    "checkpoint": _checkpoint,
    "recommend": _recommend,
    "verify": _verify,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI input, invoke continuity policy, and emit one JSON result."""

    args = _parser().parse_args(argv)
    if args.command == "hook-event":
        return _hook_event(args.harness.lower())
    try:
        store = SessionContinuityStore()
        document = _COMMANDS[args.command](args, store)
        print(json.dumps(document))
        return 0
    except (SessionContinuityError, json.JSONDecodeError, ValueError) as error:
        print(f"session-continuity: {error}", file=sys.stderr)
        return 2
