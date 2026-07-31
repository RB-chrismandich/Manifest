#!/usr/bin/env python3
"""Check files against the Code Constitution. Thin shim over constitution.cli."""

import sys

# No __pycache__ beside the deployed scripts. The importing script — not the
# imported module — decides this, and an orphaned cache directory in a tree that
# apm and bootstrap own has previously caused them to decline it.
sys.dont_write_bytecode = True

from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from constitution.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
