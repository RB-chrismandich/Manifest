#!/usr/bin/env python3
# help-coverage: covered by tests/bats/help_coverage.bats
"""manifest-delegate dispatcher — executable entry point.

Stdlib-only CLI that routes delegation/second-opinion/review/gate work to an
extensible backend registry (config/backends.json). See
specs/675-multi-agent-delegation/contracts/delegate-cli.md for the full
subcommand contract.

The implementation lives in the sibling `manifest_delegate` package: this file
grew past the Code Constitution's 500-line file ceiling (CON-002), and D5 in
research.md was amended to place the dispatcher in a package rather than a
single module. Nothing else about D5 changed — still stdlib-only, still one
process, still no backend-name branching.

This file stays the entry point because the plugin's hooks, its skills, and the
CLI contract all invoke `scripts/delegate.py` by path. It re-exports the
package's names so `import delegate` still exposes the whole surface; see the
package docstring for why a module-level CONSTANT must be patched on its owning
submodule (`delegate.transfer.SESSIONS_CAPTURE_FILE`) rather than here.
"""

import sys

# --- Early interpreter version probe (D11) --------------------------------
# Must be the first executable statements and must be parseable by very old
# interpreters (no f-strings, no type hints) so the remediation message can
# always be printed.
if sys.version_info < (3, 9):  # noqa: UP036 — deliberate runtime guard, see D11
    sys.stderr.write(
        "delegate.py: unsupported Python version %s.%s — "  # noqa: UP031
        "manifest-delegate requires Python 3.9 or newer.\n"
        "Install a supported interpreter, e.g.:\n"
        "  macOS:  brew install python@3.11\n"
        "  Linux:  use your distro's python3.9+ package\n"
        "Then re-run with that interpreter's `python3` on PATH.\n"
        % (sys.version_info[0], sys.version_info[1])
    )
    sys.exit(2)

# Everything below this line may use 3.9+ syntax.
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path

_POLICY_DISTRIBUTION = "manifest-model-policy"
_POLICY_VERSION = "0.1.0"
_REEXEC_SENTINEL = "MANIFEST_DELEGATE_RUNTIME_REEXEC"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure the exact path used by the delegate imports before resolving policy.
# This makes a sibling shadow package visible to (and rejected by) the trust gate.
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)


def _trusted_editable_policy_roots():
    """Directories an editable policy distribution may legitimately live in.

    Two, and only two. The repo checkout that owns this script, for a developer
    running `plugins/.../delegate.py` in place; and the deployed
    `~/.claude/scripts` tree, which is what `~/.claude/pyproject.toml` pins as an
    editable source and therefore what every `uv sync` of the home runtime
    recreates. The home path is anchored to `~`, not to `__file__`, because the
    installed plugin copy sits under `~/.claude/plugins/cache/...` and has no
    repo above it to derive an anchor from.

    This adds no trust root: the gate already re-execs `~/.claude/.venv`, and
    `~/.claude/scripts` is the same bootstrap-owned tree beside it.
    """
    return (
        (
            Path(__file__).resolve().parents[3]
            / "configs/claude/scripts/manifest_model_policy"
        ).resolve(),
        Path(os.path.expanduser("~/.claude/scripts/manifest_model_policy")).resolve(),
    )


def _editable_source_metadata(distribution, files, module_origin):
    """True when the distribution is an editable install of a trusted source."""
    for source_policy in _trusted_editable_policy_roots():
        if module_origin != source_policy / "__init__.py":
            continue
        try:
            direct_url = json.loads(distribution.read_text("direct_url.json") or "")
        except (AttributeError, json.JSONDecodeError, ValueError):
            return False
        return (
            direct_url.get("url") == source_policy.as_uri()
            and direct_url.get("dir_info", {}).get("editable") is True
            and any(str(item) == "_manifest_model_policy.pth" for item in files)
        )
    return False


def _trusted_model_policy_distribution():
    """Import and pin policy only from the exact distribution-owned package."""
    try:
        distribution = importlib.metadata.distribution(_POLICY_DISTRIBUTION)
        spec = importlib.util.find_spec("manifest_model_policy")
        if distribution.version != _POLICY_VERSION or spec is None or not spec.origin:
            return None, True
        distribution_root = Path(distribution.locate_file("")).resolve()
        module_origin = Path(spec.origin).resolve()
        interpreter_root = Path(sys.prefix).resolve()
        files = distribution.files or ()
        owned_policy_files = {
            Path(distribution.locate_file(item)).resolve()
            for item in files
            if item.parts and item.parts[0] == "manifest_model_policy"
        }
        # A distribution rooted outside this interpreter is not the runtime's
        # own copy, so it stays untrusted here and must qualify via the editable
        # source-metadata path below. `is_relative_to` states that directly;
        # catching relative_to's ValueError said the same thing but read as a
        # swallowed error.
        installed_runtime = distribution_root.is_relative_to(interpreter_root) and (
            module_origin in owned_policy_files
        )
        source_metadata = _editable_source_metadata(distribution, files, module_origin)
        if not installed_runtime and not source_metadata:
            return None, True
        module = importlib.import_module("manifest_model_policy")
        imported_origin = Path(module.__file__ or "").resolve()
        if imported_origin != module_origin:
            sys.modules.pop("manifest_model_policy", None)
            return None, True
        return module, False
    except (ImportError, importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None, False


def _reject_untrusted_runtime_override(trusted_identity):
    """Exit when MANIFEST_RUNTIME_PYTHON names a different interpreter.

    Compared against the canonical identity, not the exec path, so an alternate
    spelling of the trusted interpreter passes and a substitute does not. The
    override never becomes the exec target; it only asserts agreement.
    """
    runtime_override = os.environ.get("MANIFEST_RUNTIME_PYTHON")
    if not runtime_override:
        return
    override = Path(runtime_override).expanduser()
    if not override.is_absolute() or override.resolve(strict=False) != trusted_identity:
        sys.stderr.write(
            "delegate.py: rejected untrusted MANIFEST_RUNTIME_PYTHON override.\n"
        )
        sys.exit(2)


def _ensure_root_model_policy_distribution(bare_help=False):
    """Re-exec through Manifest's root runtime when plain Python lacks policy.

    `bare_help` relaxes exactly one outcome: a policy distribution that is simply
    ABSENT, where the caller only asked for usage. Every tamper signal — a
    rejected runtime override, an invalid or shadowed distribution, a re-exec
    that came back still broken — still exits 2 and prints no usage, because
    those say something is wrong with this install rather than missing from it.
    """
    policy, invalid = _trusted_model_policy_distribution()
    if policy is not None:
        return policy
    # Exec target keeps the symlink. A venv's identity is the pyvenv.cfg beside
    # the interpreter *as invoked*, so resolving it first lands in the base
    # interpreter with no site-packages — and every uv-created venv symlinks
    # bin/python, which made the re-exec below unable to ever find policy.
    trusted_runtime = Path(os.path.expanduser("~/.claude/.venv/bin/python"))
    # Identity for the override comparison stays canonical, so an equivalent
    # spelling of the same interpreter is accepted and a different one is not.
    _reject_untrusted_runtime_override(trusted_runtime.resolve(strict=False))
    if invalid:
        sys.stderr.write(
            "delegate.py: trusted Manifest runtime has an invalid "
            "manifest-model-policy distribution.\n"
        )
        sys.exit(2)
    if os.environ.get(_REEXEC_SENTINEL) == "1":
        # Distinct from the `invalid` message above: the re-exec landed in an
        # interpreter that simply has no policy, which points at the runtime
        # rather than at tampering. Sharing one message sends every diagnosis
        # hunting a shadowed distribution that isn't there.
        sys.stderr.write(
            "delegate.py: re-exec into ~/.claude/.venv did not provide "
            "manifest-model-policy; re-run ./bootstrap.sh to converge the "
            "runtime.\n"
        )
        sys.exit(2)
    if trusted_runtime.is_file() and os.access(trusted_runtime, os.X_OK):
        os.environ[_REEXEC_SENTINEL] = "1"
        os.execv(
            str(trusted_runtime),
            [str(trusted_runtime), os.path.abspath(__file__), *sys.argv[1:]],
        )
    if bare_help:
        # Nothing is tampered with, the runtime is merely absent — a clean
        # checkout, a CI image, a launchd/cron PATH. Usage dispatches nothing,
        # so answering it here keeps the CLI discoverable without weakening any
        # check above.
        sys.stdout.write(_USAGE)
        sys.exit(0)
    sys.stderr.write(
        "delegate.py: Manifest root runtime is missing manifest-model-policy; "
        "re-run ./bootstrap.sh to converge ~/.claude/.venv.\n"
    )
    sys.exit(2)


_USAGE = """\
usage: delegate.py [-h] [--json] COMMAND ...

Delegate tasks/reviews to a backend registry (codex, claude, antigravity).

commands:
  task              Delegate a task (--second-opinion, --write, --resume)
  review            Standalone read-only review (--adversarial)
  status            Show a job's current state
  result            Print a job's normalized result envelope
  cancel            Cancel a queued/running job
  setup             Check backend readiness and write user config
  transfer          Transfer a session to another surface
  gate              Internal: Stop-hook review gate
  resume-candidate  Most recent resumable job for a backend

options:
  -h, --help        show this help message and exit
  --json            machine-readable JSON output

Run `delegate.py COMMAND --help` for a command's own options.
"""


def _wants_bare_help() -> bool:
    """True for a top-level `--help`/`-h` with no subcommand in front of it."""
    return len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help")


_MODEL_POLICY = None
if __name__ == "__main__":
    # Bare `--help` still runs the full trust gate; it only changes what happens
    # when the policy distribution is absent rather than tampered with. Skipping
    # the gate outright would let a poisoned runtime answer `--help` normally.
    _MODEL_POLICY = _ensure_root_model_policy_distribution(bare_help=_wants_bare_help())

# The policy package is now pinned in sys.modules before delegate modules import
# it. Direct module imports in tests skip the executable-only trust gate.

from manifest_delegate import *  # noqa: E402,F403  (documented compatibility facade)
from manifest_delegate import (  # noqa: E402,F401  (`import *` skips submodules)
    backend,
    cli,
    config,
    constants,
    envelope,
    gate,
    jobs_cli,
    jobstore,
    process,
    readiness,
    registry,
    review,
    setup,
    task,
    transfer,
    worker,
)
from manifest_delegate.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
