#!/usr/bin/env python3
"""Run the bundle-local smoke catalog orchestrator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))

from smoke_orchestrator.cli import main  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(main())
