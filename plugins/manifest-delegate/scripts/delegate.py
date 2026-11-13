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
import os
from pathlib import Path

_REEXEC_SENTINEL = "MANIFEST_DELEGATE_RUNTIME_REEXEC"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure the exact path used by the delegate imports before resolving policy.
# This makes a sibling shadow package visible to (and rejected by) the trust gate.
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)


from manifest_delegate_policy import _trusted_model_policy_distribution  # noqa: E402


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


def _ensure_root_model_policy_distribution():
    """Prefer a qualified installed policy; otherwise use trusted release bytes.

    Existing home runtimes remain supported, but a standalone plugin ships
    everything needed for the policy import. Invalid/shadowed distributions
    still fail closed and never trigger the bundled fallback.
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
    from manifest_delegate_policy import load_bundled_policy

    try:
        return load_bundled_policy()
    except (ImportError, OSError) as error:
        sys.stderr.write(f"delegate.py: bundled model policy unavailable: {error}\n")
        sys.exit(2)


_MODEL_POLICY = None
if __name__ == "__main__":
    # Help and dispatch share the trust gate; missing policy uses release bytes.
    _MODEL_POLICY = _ensure_root_model_policy_distribution()

# The policy package is now pinned in sys.modules before delegate modules import
# it. Direct imports use the same shared gate in manifest_delegate.__init__.

from manifest_delegate import *  # noqa: E402,F403  (documented compatibility facade)
from manifest_delegate.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
