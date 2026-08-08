"""manifest-delegate: cli."""

import argparse
import sys

from . import (
    backend,
    config,
    constants,
    gate,
    jobs_cli,
    registry,
    review,
    setup,
    task,
    transfer,
    worker,
)

_SUBCOMMAND_HELP = {
    "task": "Delegate a task (optionally --second-opinion, --write, --resume).",
    "review": "Run a standalone read-only review (optionally --adversarial).",
    "status": "Show a job's current state.",
    "result": "Print a job's normalized result envelope.",
    "cancel": "Cancel a queued/running job.",
    "setup": "Check backend readiness and write user config.",
    "transfer": "Transfer a session to another surface (backend-declared).",
    "gate": "Internal: invoked by the Stop hook for the review gate.",
    "resume-candidate": "Find the most recent resumable job for a backend.",
}
_IMPLEMENTED_SUBCOMMANDS = {
    "task",
    "review",
    "status",
    "result",
    "cancel",
    "transfer",
    "resume-candidate",
    "setup",
    "gate",
}


def _positive_int_arg(raw):
    """argparse `type=` for --budget: reject non-positive/non-integer values."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--budget must be an integer, got {raw!r}"
        ) from exc
    # Reuse the config-layer rule so the CLI and config agree on "positive int".
    if not config._is_positive_int(value):
        raise argparse.ArgumentTypeError(
            f"--budget must be a positive integer, got {raw!r}"
        )
    return value


def _add_task_args(p):
    """Add `task` subcommand arguments."""
    p.add_argument("--backend", help="backend id or alias")
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--background", action="store_true", help="run detached, print job_id"
    )
    group.add_argument(
        "--wait", action="store_true", help="run in foreground (default)"
    )
    p.add_argument("--write", action="store_true", help="allow sandboxed writes")
    p.add_argument("--model", help="model tier")
    p.add_argument(
        "--budget", type=_positive_int_arg, help="budget in seconds (positive integer)"
    )
    resume_group = p.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume", metavar="JOB_ID", help="resume a prior job's session"
    )
    resume_group.add_argument(
        "--resume-last", action="store_true", help="resume the newest resumable job"
    )
    resume_group.add_argument(
        "--fresh", action="store_true", help="skip resume, start fresh"
    )
    p.add_argument(
        "--second-opinion",
        action="store_true",
        help="get a second opinion on a prior job",
    )
    p.add_argument("--of", metavar="JOB_ID", help="job id the second opinion is about")
    p.add_argument("--prompt-file", metavar="FILE", help="read the prompt from FILE")
    p.add_argument(
        "prompt", nargs="?", default=None, help="prompt text, or - for stdin"
    )


def _add_review_args(p):
    """Add `review` subcommand arguments."""
    p.add_argument("--backend", help="backend id or alias")
    p.add_argument(
        "--adversarial",
        nargs="*",
        default=None,
        metavar="FOCUS",
        help="challenge-the-design review; optional free-text focus",
    )
    p.add_argument(
        "--base", metavar="REF", default=None, help="base ref to diff against"
    )
    p.add_argument(
        "--scope",
        choices=["auto", "working-tree", "branch"],
        default="auto",
        help="diff scope (default: auto)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--background", action="store_true", help="run detached, print job_id"
    )
    group.add_argument(
        "--wait", action="store_true", help="run in foreground (default)"
    )
    p.add_argument("--model", help="model tier")
    p.add_argument(
        "--budget", type=_positive_int_arg, help="budget in seconds (positive integer)"
    )


def _add_setup_args(p):
    """Add `setup` subcommand arguments."""
    p.add_argument("--backend", help="backend id or alias")
    p.add_argument(
        "--enable-review-gate",
        action="store_true",
        help="enable the finish-time review gate",
    )
    p.add_argument("--gate-backend", help="backend id for the review gate")
    p.add_argument(
        "--disable-review-gate",
        action="store_true",
        help="disable the finish-time review gate",
    )


def _add_subcommand_args(name, p):
    """Dispatch to the per-subcommand argument builder for `name`."""
    if name == "task":
        _add_task_args(p)
    elif name == "status":
        p.add_argument(
            "job_id", nargs="?", default=None, help="job id or unique prefix"
        )
        p.add_argument("--all", action="store_true", help="show all jobs")
        p.add_argument(
            "--wait", action="store_true", help="poll until terminal or timeout"
        )
        p.add_argument(
            "--timeout", type=int, default=None, help="max seconds to --wait"
        )
    elif name in ("result", "cancel"):
        p.add_argument(
            "job_id", nargs="?", default=None, help="job id or unique prefix"
        )
    elif name == "transfer":
        p.add_argument("--backend", help="backend id or alias")
        p.add_argument(
            "--source", metavar="TRANSCRIPT", help="transcript path to import"
        )
    elif name == "review":
        _add_review_args(p)
    elif name == "resume-candidate":
        p.add_argument("--backend", help="backend id or alias")
    elif name == "setup":
        _add_setup_args(p)
    elif name == "gate":
        p.add_argument(
            "--transcript",
            required=True,
            metavar="PATH",
            help="path to the session transcript JSONL",
        )
        p.add_argument(
            "--stop-hook-active",
            action="store_true",
            help="harness re-entry indicator (at-most-once)",
        )
        # Hidden: force the gate enabled without writing config, for smoke tests.
        p.add_argument(
            "--enable-review-gate-for-test", action="store_true", help=argparse.SUPPRESS
        )


def build_parser():
    """Build the top-level argparse parser and all delegate.py subcommands."""
    parser = transfer.ShortHelpParser(
        prog="delegate.py",
        description="Delegate tasks/reviews to a backend registry (codex, claude, antigravity).",
        add_help=True,
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable JSON output"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    for name in constants.SUBCOMMANDS:
        p = sub.add_parser(name, help=_SUBCOMMAND_HELP.get(name, ""))
        if name not in _IMPLEMENTED_SUBCOMMANDS:
            continue
        p.add_argument(
            "--json", action="store_true", help="machine-readable JSON output"
        )
        _add_subcommand_args(name, p)

    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "_worker":
        if len(argv) < 3:
            sys.stderr.write("delegate.py _worker: missing job_id/workspace_dir\n")
            return 2
        return worker.cmd_worker(argv[1], argv[2])

    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        sys.stderr.write(
            "delegate: unrecognized arguments: {}\n".format(" ".join(unknown))
        )
        return 2
    if args.command is None:
        parser.print_help()
        return 0

    if args.command in ("task", "review", "status", "result", "cancel", "setup"):
        backends = registry.load_registry_or_exit(backend._registry_path_override())
        user_config = config.load_user_config()
        services_disabled = config.load_services_disabled()
        if args.command == "setup":
            return setup.cmd_setup(args, backends, user_config, services_disabled)
        if args.command == "task":
            return task.cmd_task(args, backends, user_config, services_disabled)
        if args.command == "review":
            return review.cmd_review(args, backends, user_config, services_disabled)
        if args.command == "status":
            return jobs_cli.cmd_status(args)
        if args.command == "result":
            return jobs_cli.cmd_result(args)
        if args.command == "cancel":
            return jobs_cli.cmd_cancel(args)

    if args.command in ("transfer", "resume-candidate"):
        backends = registry.load_registry_or_exit(backend._registry_path_override())
        user_config = config.load_user_config()
        if args.command == "transfer":
            return transfer.cmd_transfer(args, backends, user_config)
        if args.command == "resume-candidate":
            return transfer.cmd_resume_candidate(args, backends, user_config)

    if args.command == "gate":
        backends = registry.load_registry_or_exit(backend._registry_path_override())
        user_config = config.load_user_config()
        services_disabled = config.load_services_disabled()
        return gate.cmd_gate(args, backends, user_config, services_disabled)

    # Phase 2 only implements registry/config/job-store/envelope plumbing;
    # remaining subcommand behaviors are scaffolded stubs (Phase 3+ user stories).
    sys.stderr.write(f"delegate.py {args.command}: not yet implemented (Phase 3+)\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
