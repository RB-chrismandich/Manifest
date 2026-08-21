"""manifest-delegate: transfer."""

import argparse
import json
import os
import subprocess
import sys
import time

from . import backend, jobstore, registry, task


class ShortHelpParser(argparse.ArgumentParser):
    """ArgumentParser that exits 0 on --help/-h (argparse default) and exits
    2 with a usage message on argument errors, per the CLI exit-code
    contract (0/1/2/3)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.exit(2)


TRANSCRIPT_PATH_ENV = "MANIFEST_TRANSCRIPT_PATH"
TRANSCRIPT_ROOTS = (
    os.path.expanduser("~/.claude/projects"),
    os.path.expanduser("~/.claude/transcripts"),
)


def _validate_transcript_source(path):
    """Canonicalize `path` and require it resolve under an allowed transcript
    root. Returns (real_path, None) on success, (None, error_message) on
    rejection. Path-traversal guard for `transfer --source` (T013)."""
    real = os.path.realpath(os.path.expanduser(path))
    for root in TRANSCRIPT_ROOTS:
        real_root = os.path.realpath(root)
        if real == real_root or real.startswith(real_root + os.sep):
            return real, None
    return None, (
        "source path {!r} does not resolve under an allowed transcript root "
        "({})".format(path, " or ".join(TRANSCRIPT_ROOTS))
    )


def _run_app_server(entry, exe, source_path):
    """One `<exe> app-server` importExternalSession call.

    Returns (completed_process, None) or (None, error_message); every failure
    mode names the backend so the caller can report it verbatim.
    """
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "importExternalSession",
        "params": {"path": source_path},
    }
    try:
        proc = subprocess.run(
            [exe, "app-server"],
            input=(json.dumps(request) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            timeout=30,
        )
    except FileNotFoundError:
        return None, "backend {!r} executable {!r} not found on PATH".format(
            entry["id"], exe
        )
    except subprocess.TimeoutExpired:
        return None, "app-server import for backend {!r} timed out after 30s".format(
            entry["id"]
        )
    except OSError as exc:
        return None, "app-server import for backend {!r} failed: {}".format(
            entry["id"], exc
        )
    return proc, None


def _thread_id_from_jsonl(raw):
    """First thread id in a JSON-lines app-server response, or None.

    The stream interleaves protocol chatter with the reply, so non-JSON and
    non-object lines are skipped rather than treated as an error.
    """
    for line in raw.splitlines():
        if not line or line[0] != '{':
            if not line.strip() or line.lstrip()[:1] != '{':
                continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        result = obj.get("result")
        if isinstance(result, dict) and result.get("thread_id"):
            return result["thread_id"]
        if obj.get("thread_id"):
            return obj["thread_id"]
    return None


def _app_server_import(entry, source_path):
    """Short-lived direct `<backend executable> app-server` external-session
    import call. Executable comes from the registry entry's own `invoke`
    argv (never a hardcoded backend name) so this stays generic to any
    backend declaring `transfer.method == "app_server_import"` (FR-016).
    Returns (thread_id, None) or (None, error_message)."""
    invoke = entry.get("invoke") or []
    if not invoke:
        return None, "backend {!r} has no invoke command configured".format(entry["id"])
    exe = invoke[0]
    proc, run_error = _run_app_server(entry, exe, source_path)
    if run_error:
        return None, run_error

    raw = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    thread_id = _thread_id_from_jsonl(raw)
    if not thread_id:
        return None, (
            "app-server import for backend {!r} returned no thread id (output: {})".format(
                entry["id"], raw[:200]
            )
        )
    return thread_id, None


def cmd_resume_candidate(args, backends, user_config):
    """`resume-candidate` — report the newest resumable job for a backend so
    the delegate skill can offer continue-vs-fresh (T012)."""
    backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = registry.resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        sys.stderr.write(
            f"delegate: unknown backend {backend_name!r} (known: {known})\n"
        )
        return 2

    store = jobstore.JobStore()
    record = None
    if entry.get("resume"):
        record = task._find_last_job_for_backend(store, entry["id"])

    if record is None:
        result = {
            "available": False,
            "job_id": None,
            "backend": entry["id"],
            "session_ref": None,
            "age": None,
        }
    else:
        updated_at = record.get("updated_at") or record.get("created_at") or time.time()
        result = {
            "available": True,
            "job_id": record.get("job_id"),
            "backend": entry["id"],
            "session_ref": record.get("session_ref"),
            "age": max(0.0, time.time() - float(updated_at)),
        }

    if args.json:
        print(json.dumps(result))
    elif result["available"]:
        print(
            "resumable job {} on backend {} (age {:.0f}s)".format(
                result["job_id"], result["backend"], result["age"]
            )
        )
    else:
        print("no resumable job found for backend {}".format(entry["id"]))
    return 0


def _resolve_transfer_entry(args, backends, user_config):
    """Resolve the backend registry entry for `transfer`. Returns (entry, error_message)."""
    backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = registry.resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        return None, f"delegate: unknown backend {backend_name!r} (known: {known})\n"
    return entry, None


SESSIONS_CAPTURE_FILE = os.path.expanduser("~/.manifest/delegate/sessions.json")


def _captured_sessions_for_cwd(cwd=None):
    """Every SessionStart-captured entry whose workspace canonicalizes to `cwd`,
    as a list of (session_id, entry) pairs. Never raises; unreadable or
    malformed capture files read as "nothing captured".

    `cwd` is compared by realpath, so a symlinked checkout does not masquerade
    as a different workspace. With `cwd` omitted no scoping is possible and
    every captured entry is returned — the caller must then disambiguate.
    """
    try:
        with open(SESSIONS_CAPTURE_FILE, encoding="utf-8") as fh:
            sessions = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(sessions, dict):
        return []
    pairs = [(k, v) for k, v in sessions.items() if isinstance(v, dict)]
    if not cwd:
        return pairs
    real_cwd = os.path.realpath(cwd)
    return [p for p in pairs if os.path.realpath(p[1].get("cwd") or "") == real_cwd]


def _session_captured_transcript(cwd=None):
    """The SessionStart-captured transcript path for `cwd`, or None.

    Fails closed in both directions: None when nothing matches (never leak an
    unrelated workspace's transcript) and None when MORE than one session
    matches. Two agent sessions open in the same worktree both capture an entry
    here, and nothing in a `transfer` invocation identifies which one is asking
    — picking either would hand the caller the other session's full transcript.
    Callers that can report an error should use `_captured_sessions_for_cwd`
    and say why, rather than treating ambiguity as "not found".
    """
    matching = _captured_sessions_for_cwd(cwd)
    if len(matching) != 1:
        return None
    return matching[0][1].get("transcript_path")


def _resolve_transfer_source(args):
    """Resolve and validate the transcript source path. Returns (real_source, error_message).

    Only an explicit --source is accepted. `transfer` deliberately performs NO
    automatic transcript inference, because a `transfer` invocation carries no
    trustworthy identity of the *calling* session:

    - the SessionStart cwd-capture is keyed by workspace, so in a shared worktree
      even the sole match can be a concurrent, unrelated session's transcript
      (e.g. when the caller's own capture failed, timed out, or predates install), and
    - an ambient env var is inherited and can go stale across sessions, so it
      cannot be bound to *this* invocation either.

    Either channel could silently hand another session's full transcript to the
    backend. So the caller must name the transcript. --source is required by the
    parser; this guard is the defensive backstop (and the unit-test contract)."""
    source = args.source
    if not source:
        return None, (
            "delegate: --source required — transfer never infers the "
            "transcript (a workspace can host multiple sessions and none of "
            "them identifies the caller); pass --source <transcript>\n"
        )
    real_source, path_error = _validate_transcript_source(source)
    if path_error:
        return None, f"delegate: {path_error}\n"
    return real_source, None


def _check_transfer_method(entry, args):
    """Verify the backend supports session import. Prints on failure. Returns exit code or None."""
    transfer_cfg = entry.get("transfer")
    if transfer_cfg is None:
        message = (
            "backend {!r} does not support session import; run "
            "`delegate.py task --backend {}` to re-send context fresh".format(
                entry["id"], entry["id"]
            )
        )
        if args.json:
            print(
                json.dumps(
                    {"backend": entry["id"], "supported": False, "message": message}
                )
            )
        else:
            print(f"delegate: {message}")
        return 1

    method = transfer_cfg.get("method")
    if method != "app_server_import":
        sys.stderr.write(
            "delegate: backend {!r} transfer method {!r} not recognized\n".format(
                entry["id"], method
            )
        )
        return 1
    return None


def _print_transfer_result(args, entry, thread_id, resume_cmd):
    """Print the transfer result as JSON or plain text."""
    if args.json:
        print(
            json.dumps(
                {
                    "backend": entry["id"],
                    "supported": True,
                    "thread_id": thread_id,
                    "resume_command": resume_cmd,
                }
            )
        )
    else:
        print("backend: {}".format(entry["id"]))
        print(f"thread_id: {thread_id}")
        print(f"resume: {resume_cmd}")


def cmd_transfer(args, backends, user_config):
    """`transfer` — session handover (FR-015): registry-driven, no
    backend-name branching (FR-016) (T013)."""
    entry, entry_error = _resolve_transfer_entry(args, backends, user_config)
    if entry_error:
        sys.stderr.write(entry_error)
        return 2

    real_source, source_error = _resolve_transfer_source(args)
    if source_error:
        sys.stderr.write(source_error)
        return 2

    method_exit = _check_transfer_method(entry, args)
    if method_exit is not None:
        return method_exit

    if not args.json:
        print(f"source: {real_source}")

    thread_id, import_error = _app_server_import(entry, real_source)
    if import_error:
        sys.stderr.write(f"delegate: {import_error}\n")
        return 1

    mapping = {"output_file": "<job-output-file>"}
    resume_argv = backend.build_resume_argv(entry, thread_id, False, None, mapping)
    resume_cmd = " ".join(resume_argv)
    _print_transfer_result(args, entry, thread_id, resume_cmd)
    return 0
