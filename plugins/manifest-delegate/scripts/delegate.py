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

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure the exact path used by the delegate imports before resolving policy.
# This makes a sibling shadow package visible to (and rejected by) the trust gate.
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)


from manifest_delegate_policy import ensure_runtime_policy  # noqa: E402

_MODEL_POLICY = None
if __name__ == "__main__":
    # Help and dispatch share the trust gate; missing policy uses release bytes.
    _MODEL_POLICY = ensure_runtime_policy(__file__)

# The policy package is now pinned in sys.modules before delegate modules import
# it. Direct imports use the same shared gate in manifest_delegate.__init__.

from manifest_delegate import *  # noqa: E402,F403  (documented compatibility facade)
from manifest_delegate.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
