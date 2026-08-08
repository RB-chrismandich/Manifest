#!/usr/bin/env python3
"""In-process handles shared by the delegate unit tests.

`delegate` is loaded ONCE here and imported by every unit-level test module, so
a monkeypatch applied in one test sees the same module object the code under
test uses. Loading it per file would give each file its own copy — harmless
until two files disagree about which one a helper patched.

Distinct from _delegate_harness.py, which builds the throwaway workspace and
stub backend for the tests that drive delegate.py as a SUBPROCESS. This module
is for the tests that call into it directly.

Patch targets: `delegate` is the entry-point facade, so a module-level CONSTANT
must be patched on the submodule that owns it (delegate.transfer.
SESSIONS_CAPTURE_FILE, delegate.readiness._run_readiness_probe, ...). Rebinding
the flat name on the facade would change nothing the code reads.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "plugins" / "manifest-delegate" / "scripts" / "delegate.py"


def _load_delegate():
    spec = importlib.util.spec_from_file_location("delegate", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


delegate = _load_delegate()


def _valid_backend(id_="codex", aliases=None):
    return {
        "id": id_,
        "aliases": aliases or [],
        "display_name": id_.title(),
        "binary": id_,
        "invoke": [id_, "exec", "{prompt}"],
        "resume": None,
        "model_args": ["--model", "{model}"],
        "tier_source": id_,
        "default_tier": "auto",
        "session_id_capture": {"mode": "none"},
        "input": {
            "transport": "stdin",
            "max_payload_bytes": 1000000,
            "max_context_bytes": None,
        },
        "readiness": {
            "version_cmd": [id_, "--version"],
            "auth_probe_cmd": [id_, "whoami"],
            "install_fix": f"install {id_}",
            "login_fix": f"login {id_}",
        },
        "sandbox": {
            "read_only_args": ["--read-only"],
            "write_args": ["--write"],
        },
        "prompting_ref": f"skills/delegate/references/{id_}.md",
        "services_key": id_,
    }
