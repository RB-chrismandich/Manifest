"""CLI subcommands, backend probe, per-repo lock, exit-code mapping
(contracts/cli-interface.md; FR-012, FR-016).

The lock mirrors the loop_lock.sh local-file pattern: one active run per
target repo, `${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/locks/<repo-slug>.lock`
(state-root confined per FR-017), stale (reclaimable) once older than the run
wall-clock ceiling — a live run cannot legitimately outlast it.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import AbortError, PreflightError
from .gitops import repo_root_of
from .loop import RunConfig, answer_run, blocking_summary, start_run
from .persistence import (
    RunStore,
    default_state_root,
    new_run_id,
    repo_slug,
    utcnow_iso,
)


def err(message: str) -> None:
    print(f"cddl-loop: {message}", file=sys.stderr)


def _probe_backend(cli: str) -> None:
    if shutil.which(cli) is None:
        raise PreflightError(
            f"no usable backend: '{cli}' not found on PATH — install and log in "
            "the claude CLI (claude /login) or point CDDL_CLI at one (FR-012)"
        )
    # Auth half of FR-012: `claude auth status --json` is a non-model probe.
    # Best-effort/fail-open — a seam CLI without the subcommand must not be
    # refused here; only positive logged-out evidence fails pre-flight.
    try:
        proc = subprocess.run(
            [cli, "auth", "status", "--json"],
            input="",
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    combined = (proc.stdout or "") + (proc.stderr or "")
    if '"loggedIn": false' in combined or '"loggedIn":false' in combined:
        raise PreflightError(
            f"no usable backend: '{cli}' is installed but not logged in — run "
            f"`{cli} /login` (FR-012)"
        )


class RepoLock:
    """One active run per target repo (contracts/cli-interface.md Concurrency).

    Lives under the state root — the spec's designated out-of-tree write area
    (FR-017) — not /tmp; staleness is mtime-based against the run ceiling.
    """

    def __init__(self, repo_root, stale_s: float, state_root=None):
        lock_root = Path(state_root or default_state_root()) / "cddl" / "locks"
        self.path = lock_root / f"{repo_slug(repo_root)}.lock"
        self.stale_s = float(stale_s)

    def acquire(self, run_hint: str = "") -> RepoLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in (1, 2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue  # released between check and stat; retry
                if age <= self.stale_s:
                    owner = "unknown"
                    with contextlib.suppress(OSError, json.JSONDecodeError):
                        content = self.path.read_text(encoding="utf-8")
                        if '"run"' in content:
                            owner = json.loads(content).get("run", "unknown")
                    raise PreflightError(
                        f"another cddl run is active for this repo (run {owner}; "
                        f"lock {self.path}, reclaimable after {int(self.stale_s)}s)"
                    ) from None
                self.path.unlink(missing_ok=True)  # stale — reclaim
                continue
            with os.fdopen(fd, "w") as handle:
                handle.write(
                    json.dumps(
                        {"pid": os.getpid(), "run": run_hint, "created": utcnow_iso()}
                    )
                )
            return self
        raise PreflightError(f"could not acquire run lock: {self.path}")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cddl_loop.py",
        description="Critic-Driven Development Loop (two-phase, critic-gated).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="pre-flight + clarification gate + loop")
    start.add_argument(
        "target", help="speckit feature dir or superpowers design doc root"
    )
    start.add_argument("--spec", help="explicit spec path (wins over detection)")
    start.add_argument("--plan", help="explicit plan path (wins over detection)")
    start.add_argument("--verify-cmd", dest="verify_cmd")
    start.add_argument("--max-rounds", dest="max_rounds", type=int)
    start.add_argument("--max-iterations", dest="max_iterations", type=int)
    start.add_argument("--invoke-timeout", dest="invoke_timeout_s", type=float)
    start.add_argument("--run-timeout", dest="run_timeout_s", type=float)
    start.add_argument(
        "--allow-dirty", dest="allow_dirty", action="store_true", default=None
    )
    start.add_argument("--state-root", dest="state_root")

    answer = sub.add_parser("answer", help="resume a parked run with operator answers")
    answer.add_argument("--run", required=True, dest="run_id")
    answer.add_argument("--answers-file", required=True, dest="answers_file")
    answer.add_argument("--state-root", dest="state_root")

    status = sub.add_parser("status", help="print a run's state summary")
    status.add_argument("--run", dest="run_id")
    status.add_argument("--state-root", dest="state_root")
    return parser


def _config(args) -> RunConfig:
    return RunConfig.from_env(
        max_rounds=getattr(args, "max_rounds", None),
        max_iterations=getattr(args, "max_iterations", None),
        invoke_timeout_s=getattr(args, "invoke_timeout_s", None),
        run_timeout_s=getattr(args, "run_timeout_s", None),
        verify_cmd=getattr(args, "verify_cmd", None),
        allow_dirty=getattr(args, "allow_dirty", None),
    )


def _state_root(args) -> Path:
    return (
        Path(args.state_root)
        if getattr(args, "state_root", None)
        else default_state_root()
    )


def _locate_store(state_root, run_id: str) -> RunStore:
    """cwd repo first; else search the state root by run id (contract:
    `answer`/`status --run` work from anywhere)."""
    with contextlib.suppress(PreflightError):
        return RunStore.open(state_root, repo_root_of(os.getcwd()), run_id)
    store = RunStore.find(state_root, run_id)
    if store is None:
        raise PreflightError(f"no such run: {run_id} (under {state_root})")
    return store


def _report_outcome(outcome) -> int:
    if outcome.exit_code == 0:
        print(f"cddl-loop: {outcome.message}")
    else:
        err(outcome.message)
    return outcome.exit_code


def cmd_start(args) -> int:
    config = _config(args)
    _probe_backend(config.cli)
    repo_root = repo_root_of(args.target)
    run_id = new_run_id()  # pre-generated so the lock can name its owning run
    lock = RepoLock(repo_root, config.run_timeout_s, _state_root(args)).acquire(
        run_hint=run_id
    )
    try:
        outcome = start_run(
            args.target,
            config,
            state_root=_state_root(args),
            spec=args.spec,
            plan=args.plan,
            run_id=run_id,
        )
    finally:
        lock.release()
    return _report_outcome(outcome)


def cmd_answer(args) -> int:
    config = _config(args)
    _probe_backend(config.cli)
    answers_path = Path(args.answers_file)
    if not answers_path.is_file():
        err(f"answers file not found: {answers_path}")
        return 2
    state_root = _state_root(args)
    store = _locate_store(state_root, args.run_id)
    repo_root = store.repo_root
    lock = RepoLock(repo_root, config.run_timeout_s, state_root).acquire(
        run_hint=args.run_id
    )
    try:
        outcome = answer_run(
            repo_root,
            args.run_id,
            answers_path.read_text(encoding="utf-8"),
            config,
            state_root=state_root,
        )
    finally:
        lock.release()
    return _report_outcome(outcome)


def cmd_status(args) -> int:
    state_root = _state_root(args)
    if args.run_id:
        store = _locate_store(state_root, args.run_id)
    else:
        store = RunStore.latest(state_root, repo_root_of(os.getcwd()))
        if store is None:
            raise PreflightError(
                f"no cddl runs recorded for this repository under {state_root}"
            )
    state = store.read_state()
    print(f"run:      {state['run_id']}")
    print(f"status:   {state['status']}  (phase: {state['phase']})")
    print(f"branch:   {state['branch']}")
    print(f"rounds:   {len(state.get('clarification_rounds') or [])}")
    print(f"iters:    {len(state.get('iterations') or [])}")
    written = state.get("written_paths") or []
    disposition = "staged" if state.get("staged") else "unstaged"
    print(f"written:  {len(written)} path(s) [{disposition}]")
    if state["status"] == "questions_pending":
        print(f"questions: {store.run_dir / 'questions.md'}")
    for entry in blocking_summary(state):
        top = entry["outstanding"][0] if entry["outstanding"] else ""
        print(f"blocking: {entry['role_key']} — {top}")
    print(f"run dir:  {store.run_dir}")
    print(f"report:   {state.get('report_path', '-')}")
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: 2 on usage error, 0 on -h
        return int(exc.code or 0)
    handlers = {"start": cmd_start, "answer": cmd_answer, "status": cmd_status}
    try:
        return handlers[args.command](args)
    except PreflightError as exc:
        err(str(exc))
        return 6
    except AbortError as exc:
        err(str(exc))
        return 7
    except KeyboardInterrupt:
        err("interrupted — persisted run artifacts survive; see `status` (FR-016)")
        return 7
