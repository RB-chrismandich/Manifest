#!/usr/bin/env python3
"""Generic stub backend CLI for delegate.py job-lifecycle tests (T009).

Behavior is driven entirely by a JSON control file named in the
STUB_CONTROL_FILE env var (inherited from the test's subprocess env), so the
same executable can impersonate any registry backend across tests.

Control file keys (all optional):
  sleep              seconds to sleep before doing anything else (timeout tests)
  drain_stdin        bool; read+discard stdin (default True)
  session_format     "jsonl_event" | "json_field" | "output_scan" | None
  session_ref        string emitted per session_format (default "sess-stub")
  envelope           dict; if present, printed as a fenced ```json block
  raw_text           string; if present (and no envelope), printed verbatim
  write_outfile_flag argv flag name preceding the destination path
                     (e.g. "--outfile"); when present, content is written
                     there instead of/in addition to stdout
  outfile_content    string content for write_outfile_flag
  exit_code          process exit code (default 0)
  sentinel_file      path; written unconditionally on process start, before
                     the `sleep` delay — proves the backend executable
                     actually ran (used by cancel-race regression tests)
"""

import contextlib
import json
import os
import sys


def _load_control():
    """The control file the harness wrote for this invocation, or {}."""
    control_path = os.environ.get("STUB_CONTROL_FILE")
    if control_path and os.path.exists(control_path):
        with open(control_path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _simulate_process_behavior(control):
    """Impersonate the timing/lifetime quirks a real backend can exhibit."""
    sentinel_file = control.get("sentinel_file")
    if sentinel_file:
        with open(sentinel_file, "w", encoding="utf-8") as fh:
            fh.write("ran\n")

    # Detached descendant that inherits (holds open) this process's stdout, then
    # this backend exits. Exercises the dispatcher's bounded-drain guard: the
    # stdout pipe stays open past exit, so an unbounded reader.join would hang.
    detached_holder_secs = control.get("detached_holder_secs")
    if detached_holder_secs:
        import subprocess

        # `holder_in_group` keeps the holder in THIS backend's process group
        # (no new session), so it is reachable by the dispatcher's killpg on the
        # recorded pgid — the realistic runaway-child case. Default True keeps a
        # fully-detached holder (start_new_session) for the pure no-hang test.
        in_group = bool(control.get("holder_in_group"))
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"import time,sys; time.sleep({int(detached_holder_secs)})",
            ],
            start_new_session=not in_group,
        )  # inherits stdout; not waited on

    sleep_s = control.get("sleep", 0)
    if sleep_s:
        import time

        time.sleep(sleep_s)

    if control.get("drain_stdin", True) and not sys.stdin.isatty():
        # A read error here is irrelevant to the behavior being impersonated.
        with contextlib.suppress(Exception):
            sys.stdin.read()


def _emit_output(control):
    """Write the session id, side files, and result envelope a backend would."""
    session_ref = control.get("session_ref", "sess-stub")
    session_format = control.get("session_format")
    if session_format == "jsonl_event":
        print(json.dumps({"type": "thread.started", "thread_id": session_ref}))
    elif session_format == "json_field":
        print(json.dumps({"session_id": session_ref}))
    elif session_format == "output_scan":
        print(f"session: {session_ref}")

    outfile_flag = control.get("write_outfile_flag")
    if outfile_flag:
        for i, arg in enumerate(sys.argv):
            if arg == outfile_flag and i + 1 < len(sys.argv):
                with open(sys.argv[i + 1], "w", encoding="utf-8") as fh:
                    fh.write(control.get("outfile_content", ""))

    prefix_bytes = control.get("prefix_bytes")
    if prefix_bytes:
        # Emit a large filler prefix before the envelope to exercise the
        # dispatcher's bounded (tail-retaining) output capture.
        sys.stdout.write("A" * int(prefix_bytes) + "\n")

    envelope = control.get("envelope")
    if envelope is not None:
        print("```json")
        print(json.dumps(envelope))
        print("```")
    elif "raw_text" in control:
        print(control["raw_text"])


def main():
    control = _load_control()
    _simulate_process_behavior(control)
    _emit_output(control)
    sys.exit(int(control.get("exit_code", 0)))


if __name__ == "__main__":
    main()
