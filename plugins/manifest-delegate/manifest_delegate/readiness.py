"""manifest-delegate: readiness."""

import json
import re
import subprocess
import time

from . import config, constants, registry


def _run_readiness_probe(argv, timeout=10):
    """Run a readiness probe argv; return (returncode, output).

    returncode is None when the binary is missing, -1 on timeout.
    """
    if not argv:
        return 0, ""
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return None, ""
    except subprocess.TimeoutExpired:
        return -1, ""
    except OSError:
        return None, ""


def _init_readiness_row(backend_id):
    """Build the initial (pre-probe) readiness row shape."""
    return {
        "backend": backend_id,
        "state": "error",
        "version": None,
        "fix": "—",
        "identity": None,
        "probe_seconds": 0.0,
    }


def _probe_enabled_state(entry, user_config, services_disabled):
    """Check backend enablement. Returns a state/fix pair, or (None, None) if enabled."""
    enabled, layer = config.effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if enabled:
        return None, None
    if layer == "workspace services.yml":
        return (
            "disabled_workspace",
            "enable in ~/.claude/config/services.yml (workspace layer outranks user enable)",
        )
    return (
        "disabled_user",
        f"delegate.py setup with an enabled entry in delegation.json/.yml ({layer})",
    )


def _probe_retired_state(readiness):
    """Check the retired_check probe. Returns a state/fix pair, or (None, None) if not retired."""
    retired_check = readiness.get("retired_check")
    if not retired_check:
        return None, None
    rc, _out = _run_readiness_probe(retired_check, timeout=10)
    if rc == 0:
        return "retired", "backend retired; see registry notes"
    return None, None


def _probe_version_and_auth(backend_id, readiness, row):
    """Run version and auth probes, filling in `row` in place."""
    rc, out = _run_readiness_probe(readiness.get("version_cmd"), timeout=10)
    if rc is None or rc != 0:
        row["state"] = "error" if rc == -1 else "not_installed"
        row["fix"] = (
            "version probe timed out"
            if rc == -1
            else readiness.get("install_fix", f"install {backend_id}")
        )
        return
    row["version"] = out.splitlines()[0].strip() if out else None

    auth_rc, auth_out = _run_readiness_probe(
        readiness.get("auth_probe_cmd"), timeout=10
    )
    if auth_rc is None:
        row["state"] = "not_installed"
        row["fix"] = readiness.get("install_fix", f"install {backend_id}")
    elif auth_rc == -1:
        row["state"] = "error"
        row["fix"] = "auth probe timed out"
    elif auth_rc != 0:
        row["state"] = "not_authenticated"
        row["fix"] = readiness.get("login_fix", "login required")
    elif _looks_like_auth_error(auth_out):
        row["state"] = "not_authenticated"
        row["fix"] = readiness.get("login_fix", "login required")
        row["identity"] = auth_out or None
    else:
        row["state"] = "ready"
        row["fix"] = "—"
        row["identity"] = auth_out or None


_AUTH_ERROR_PATTERN = re.compile(
    r"not logged in|not authenticated|unauthorized|unauthenticated|"
    r"login required|please log ?in|please login|auth(?:entication)? error|"
    r"invalid (?:api key|token|credentials)|no (?:api key|credentials) found",
    re.IGNORECASE,
)


def _looks_like_auth_error(auth_out):
    """Detect an error string in an auth probe's output despite exit 0 (US2).

    Some backends' auth probes exit 0 even while printing a not-logged-in
    message (e.g. `devin auth status` — see parallel_agent.yml's devin note).
    Exit code alone is not a sufficient readiness signal; inspect content too.
    """
    if not auth_out:
        return False
    return bool(_AUTH_ERROR_PATTERN.search(auth_out))


def probe_backend_readiness(entry, user_config, services_disabled):
    """Probe one backend's readiness row (US2): state/version/fix/probe_seconds.

    Never blocks on interactive input (US2-AS3): every probe carries
    stdin=DEVNULL and a bounded timeout.
    """
    backend_id = entry["id"]
    readiness = entry.get("readiness", {})
    row = _init_readiness_row(backend_id)
    start = time.time()

    state, fix = _probe_enabled_state(entry, user_config, services_disabled)
    if state is None:
        state, fix = _probe_retired_state(readiness)
    if state is not None:
        row["state"], row["fix"] = state, fix
        row["probe_seconds"] = round(time.time() - start, 3)
        return row

    _probe_version_and_auth(backend_id, readiness, row)
    row["probe_seconds"] = round(time.time() - start, 3)
    return row


def _cmd_setup_gate_toggle(args, user_config=None):
    changes = {}
    if getattr(args, "enable_review_gate", False):
        changes["enabled"] = True
        if getattr(args, "gate_backend", None):
            changes["backend"] = args.gate_backend
    else:
        changes["enabled"] = False

    current = (user_config or {}).get("review_gate", {})
    budget = current.get(
        "budget_seconds", config.FACTORY_DEFAULTS["review_gate"]["budget_seconds"]
    )
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        budget = config.FACTORY_DEFAULTS["review_gate"]["budget_seconds"]
    changes["budget_seconds"] = max(1, min(budget, config.GATE_BUDGET_CAP_SECONDS))

    try:
        path, data = config.write_review_gate_config(changes)
    except registry.RegistryError as exc:
        constants.err(str(exc))
        return 2
    gate = data.get("review_gate", {})
    if getattr(args, "json", False):
        print(json.dumps({"path": path, "review_gate": gate}))
    else:
        state = "enabled" if gate.get("enabled") else "disabled"
        backend_note = (
            " (backend: {})".format(gate["backend"]) if gate.get("backend") else ""
        )
        print(f"review gate {state}{backend_note} — written to {path}")
    return 0
