#!/bin/sh
# Bounded, advisory SessionStart surface for the shared MCP health helper.

warn_degraded() {
    printf '%s\n' "MCP health: degraded ($1)"
}

if [ -n "${MANIFEST_HEALTH_PYTHON:-}" ]; then
    health_python=$MANIFEST_HEALTH_PYTHON
else
    health_python=$(command -v python3 2>/dev/null || true)
fi

if [ -z "$health_python" ] || [ ! -x "$health_python" ]; then
    warn_degraded "python_unavailable"
    exit 0
fi

data_home=${XDG_DATA_HOME:-"${HOME:-}/.local/share"}
health_helper=${MANIFEST_MCP_HEALTH_HELPER:-"$data_home/manifest/health/mcp_health.py"}
if [ ! -r "$health_helper" ]; then
    warn_degraded "helper_unavailable"
    exit 0
fi

outer_timeout=${MANIFEST_MCP_HEALTH_OUTER_TIMEOUT_SECONDS:-25}
summary=$(
    "$health_python" - "$health_helper" "$outer_timeout" <<'PY'
import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import time

MAX_OUTPUT_BYTES = 1024 * 1024
MAX_SERVERS = 1000
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
ALLOWED_REASONS = {
    "connected",
    "auth_required",
    "connection_failed",
    "timeout",
    "unavailable",
    "unparseable",
    "not_probed",
    "probe_in_progress",
}


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1)
    except (subprocess.TimeoutExpired, ChildProcessError):
        pass


def fail(reason):
    print(reason)
    return 1


def main():
    helper = sys.argv[1]
    try:
        timeout = float(sys.argv[2])
    except ValueError:
        timeout = 25.0
    if not math.isfinite(timeout):
        timeout = 25.0
    timeout = min(max(timeout, 0.1), 25.0)

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                helper,
                "--json",
                "--probe",
                "--harness",
                "claude",
                "--timeout-seconds",
                "20",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError):
        return fail("unavailable")
    if process.stdout is None:
        kill_group(process)
        return fail("unavailable")

    output = bytearray()
    eof = False
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + timeout
    try:
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                kill_group(process)
                return fail("outer_timeout")
            for key, _mask in selector.select(min(remaining, 0.1)):
                try:
                    chunk = os.read(
                        key.fd,
                        min(65536, MAX_OUTPUT_BYTES + 1 - len(output)),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    try:
                        selector.unregister(key.fd)
                    except KeyError:
                        pass
                    continue
                output.extend(chunk)
                if len(output) > MAX_OUTPUT_BYTES:
                    kill_group(process)
                    return fail("invalid_result")
            if process.poll() is not None and eof:
                break
        returncode = process.wait(
            timeout=max(0.01, deadline - time.monotonic())
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        kill_group(process)
        return fail("unavailable")
    finally:
        selector.close()
        process.stdout.close()

    try:
        report = json.loads(output.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return fail("invalid_result")
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != 1
        or report.get("harness") != "claude"
        or report.get("status") not in {"ok", "degraded"}
        or not isinstance(report.get("observed_at"), str)
        or not report["observed_at"].endswith("Z")
    ):
        return fail("invalid_result")
    servers = report.get("servers")
    if not isinstance(servers, list) or len(servers) > MAX_SERVERS:
        return fail("invalid_result")

    reasons = set()
    names = set()
    for server in servers:
        if not isinstance(server, dict):
            return fail("invalid_result")
        name = server.get("name")
        reason = server.get("reason_code")
        server_status = server.get("status")
        if (
            not isinstance(name, str)
            or not SAFE_NAME.fullmatch(name)
            or name in names
            or reason not in ALLOWED_REASONS
            or server_status not in {"healthy", "disabled", "degraded"}
        ):
            return fail("invalid_result")
        names.add(name)
        if server_status == "healthy" and reason != "connected":
            return fail("invalid_result")
        if server_status == "disabled" and reason != "not_probed":
            return fail("invalid_result")
        if server_status == "degraded":
            if reason == "connected":
                return fail("invalid_result")
            reasons.add(reason)

    derived_status = "degraded" if reasons else "ok"
    if report["status"] != derived_status:
        return fail("invalid_result")
    if returncode == 0 and derived_status == "ok":
        return 0
    if returncode == 1 and derived_status == "degraded":
        print(",".join(sorted(reasons)[:3]))
        return 1
    return fail("invalid_result")


try:
    raise SystemExit(main())
except SystemExit:
    raise
except BaseException:
    print("unavailable")
    raise SystemExit(1)
PY
)
controller_status=$?

if [ "$controller_status" -ne 0 ]; then
    case "$summary" in
        auth_required|connection_failed|timeout|unavailable|unparseable|not_probed|probe_in_progress|outer_timeout|invalid_result|python_unavailable|helper_unavailable)
            warn_degraded "$summary"
            ;;
        *,*)
            # The controller emits only allowlisted comma-separated reason codes.
            warn_degraded "$summary"
            ;;
        *)
            warn_degraded "invalid_result"
            ;;
    esac
fi

# Health degradation is advisory to session availability, never a false green.
exit 0
