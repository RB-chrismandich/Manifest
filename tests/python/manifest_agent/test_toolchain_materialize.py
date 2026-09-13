"""Behavioral contracts for toolchain environment materialization helpers."""

from pathlib import Path

import pytest

from manifest_agent.checks.toolchain_materialize import MaterializationError, load_json


def test_load_json_rejects_non_object_documents(tmp_path: Path) -> None:
    """Toolchain materialization rejects JSON that cannot supply named fields."""
    path = tmp_path / "array.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(MaterializationError, match="JSON object required"):
        load_json(path)
