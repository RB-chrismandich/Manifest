"""manifest-delegate: constants."""

import os
import re
import sys

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(PACKAGE_DIR)
SCRIPT_DIR = os.path.join(PLUGIN_DIR, "scripts")
DEFAULT_REGISTRY_PATH = os.path.join(PLUGIN_DIR, "config", "backends.json")
_PACKAGED_REGISTRY_PATH = os.path.join(PACKAGE_DIR, "config", "backends.json")
if os.path.isfile(_PACKAGED_REGISTRY_PATH):
    DEFAULT_REGISTRY_PATH = _PACKAGED_REGISTRY_PATH

# The executable entry point, not this package. A detached worker is respawned
# as `python3 <ENTRY_SCRIPT> _worker ...`, and only scripts/delegate.py runs the
# version probe and puts PLUGIN_DIR on sys.path before importing the package.
ENTRY_SCRIPT = os.path.join(SCRIPT_DIR, "delegate.py")


def worker_argv(job_id, workspace_dir, prompt_fd, attempt_id=None, start_identity=None):
    dispatch_args = [
        value for value in (prompt_fd, attempt_id, start_identity) if value is not None
    ]
    if os.path.isfile(ENTRY_SCRIPT):
        return [
            sys.executable,
            ENTRY_SCRIPT,
            "_worker",
            job_id,
            workspace_dir,
            *dispatch_args,
        ]
    return [
        sys.executable,
        "-m",
        "manifest_delegate",
        "_worker",
        job_id,
        workspace_dir,
        *dispatch_args,
    ]


DANGEROUS_TOKEN_RE = re.compile(r"dangerously|bypass", re.IGNORECASE)
SHELL_METACHAR_RE = re.compile(r"[;|&`$><\n]")
PLACEHOLDER_RE = re.compile(r"^\{[a-z_]+\}$")

SUBCOMMANDS = [
    "task",
    "review",
    "status",
    "result",
    "cancel",
    "setup",
    "transfer",
    "gate",
    "resume-candidate",
]

DELEGATIONS_DIR_ENV = "MANIFEST_DELEGATIONS_DIR"
CONFIG_DIR_ENV = "MANIFEST_CONFIG_DIR"
HOME_CONFIG_DIR = os.path.expanduser("~/.claude/config")

KEEP_LAST_N = 50


def err(message):
    sys.stderr.write(f"delegate.py: {message}\n")
