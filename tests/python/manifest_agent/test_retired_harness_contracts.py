"""Contracts from releases that predate a harness removal stay readable."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from manifest_agent.contracts import load_contract

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLE = _REPO_ROOT / "plugins" / "manifest-docs"


def _contract_with_harness(tmp_path: Path, harness: str) -> Path:
    """Copy a real bundle and declare one extra harness in its compatibility."""
    bundle = tmp_path / _BUNDLE.name
    shutil.copytree(_BUNDLE, bundle)
    path = bundle / "manifest-capabilities.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["compatibility"][harness] = dict(document["compatibility"]["claude"])
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_pre_removal_contract_naming_gemini_loads_without_it(tmp_path: Path) -> None:
    contract = load_contract(_contract_with_harness(tmp_path, "gemini"))

    assert "gemini" not in contract.compatibility
    assert "claude" in contract.compatibility


def test_contract_naming_an_unknown_harness_is_still_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_contract(_contract_with_harness(tmp_path, "not-a-harness"))
