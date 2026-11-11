"""Removing Manifest's placeholder tolerates only the host's orphan marker."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from manifest_agent.adapters.capability_native_remove import _rmdir_placeholder


@pytest.fixture
def parent(tmp_path: Path) -> Iterator[int]:
    descriptor = os.open(tmp_path, os.O_RDONLY)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def test_empty_placeholder_is_removed(tmp_path: Path, parent: int) -> None:
    (tmp_path / "placeholder").mkdir()

    _rmdir_placeholder("placeholder", parent)

    assert not (tmp_path / "placeholder").exists()


def test_host_orphan_marker_does_not_block_removal(tmp_path: Path, parent: int) -> None:
    placeholder = tmp_path / "placeholder"
    placeholder.mkdir()
    (placeholder / ".orphaned_at").write_text("1780000000", encoding="utf-8")

    _rmdir_placeholder("placeholder", parent)

    assert not placeholder.exists()


@pytest.mark.parametrize("extra", ["plugin.json", ".orphaned_at_backup"])
def test_any_other_content_still_fails_as_not_empty(
    tmp_path: Path, parent: int, extra: str
) -> None:
    placeholder = tmp_path / "placeholder"
    placeholder.mkdir()
    (placeholder / ".orphaned_at").write_text("1780000000", encoding="utf-8")
    (placeholder / extra).write_text("{}", encoding="utf-8")

    with pytest.raises(OSError, match="not empty"):
        _rmdir_placeholder("placeholder", parent)

    assert (placeholder / ".orphaned_at").exists()
    assert (placeholder / extra).exists()


def test_marker_that_is_not_a_regular_file_still_fails(
    tmp_path: Path, parent: int
) -> None:
    placeholder = tmp_path / "placeholder"
    placeholder.mkdir()
    (placeholder / ".orphaned_at").symlink_to(tmp_path / "elsewhere")

    with pytest.raises(OSError, match="not empty"):
        _rmdir_placeholder("placeholder", parent)

    assert (placeholder / ".orphaned_at").is_symlink()


def test_missing_placeholder_raises_file_not_found(parent: int) -> None:
    with pytest.raises(FileNotFoundError):
        _rmdir_placeholder("absent", parent)
