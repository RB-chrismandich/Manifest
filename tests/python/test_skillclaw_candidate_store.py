"""Model-generated candidates cannot redirect writes outside their output root."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
from skillclaw import evolve as ev


def _candidate(name, content="candidate"):
    return {"name": name, "content": content}


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "../../trusted",
        "ABSOLUTE",
        "a/b",
        "a\\b",
        ".",
        "..",
        "",
        "Upper",
        "white space",
        " leading",
        "trailing ",
        "é",
        "a--b",
        "-a",
        "a-",
        "x" * 256,
    ],
)
def test_invalid_name_rejects_whole_batch(tmp_path, name):
    if name == "ABSOLUTE":
        name = str(tmp_path / "absolute-target")
    root = tmp_path / "missing" / "candidates"
    with pytest.raises(RuntimeError):
        ev.write_candidates([_candidate("valid"), _candidate(name)], root)
    assert not root.parent.exists()
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize(
    "kind", ["root", "directory", "file", "dangling", "fifo", "nonregular"]
)
def test_unsafe_target_rejects_batch_before_any_write(tmp_path, kind):
    root = tmp_path / "candidates"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "SKILL.md"
    sentinel.write_text("trusted")
    good = root / "good"
    good.mkdir()
    (good / "SKILL.md").write_text("original")
    if kind == "root":
        root = tmp_path / "root-link"
        root.symlink_to(outside, target_is_directory=True)
    elif kind == "directory":
        (root / "bad").symlink_to(outside, target_is_directory=True)
    else:
        (root / "bad").mkdir()
        target = root / "bad" / "SKILL.md"
        if kind in ("file", "dangling"):
            target.symlink_to(sentinel if kind == "file" else outside / "absent")
        elif kind == "fifo":
            os.mkfifo(target)
        else:
            target.mkdir()
    with pytest.raises(RuntimeError):
        ev.write_candidates([_candidate("good", "changed"), _candidate("bad")], root)
    assert (good / "SKILL.md").read_text() == "original"
    assert sentinel.read_text() == "trusted"
    assert sorted(p.name for p in outside.iterdir()) == ["SKILL.md"]


def test_regular_updates_do_not_modify_outside_hardlinks(tmp_path):
    root = tmp_path / "candidates"
    (root / "update").mkdir(parents=True)
    sentinel = tmp_path / "trusted"
    sentinel.write_text("trusted")
    os.link(sentinel, root / "update" / "SKILL.md")
    assert ev.write_candidates([_candidate("update")], root) == ["update"]
    assert sentinel.read_text() == "trusted"
    assert (root / "update" / "SKILL.md").read_text() == "candidate"


def test_valid_create_update_duplicates_and_trusted_parent_alias(tmp_path):
    parent = tmp_path / "real-parent"
    parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    root = alias / "nested" / "candidates"
    assert ev.write_candidates(
        [_candidate("skill-2", "first"), _candidate("skill-2", "last")], root
    ) == ["skill-2", "skill-2"]
    assert (root / "skill-2" / "SKILL.md").read_text() == "last"
    assert ev.write_candidates([], tmp_path / "absent") == []
    assert not (tmp_path / "absent").exists()


def test_invalid_content_does_not_overwrite_valid_candidate(tmp_path):
    with pytest.raises(RuntimeError):
        ev.write_candidates(
            [_candidate("good"), _candidate("bad", "\ud800")], tmp_path / "root"
        )
    assert not (tmp_path / "root").exists()


def test_parser_keeps_invalid_model_names_for_rejection(tmp_path):
    for name in ["../outside", " padded ", ""]:
        candidates = ev.parse_candidates(
            f"~~~skill name=good\nok\n~~~\n~~~skill name={name}\nbad\n~~~"
        )
        with pytest.raises(RuntimeError):
            ev.write_candidates(candidates, tmp_path / "root")
        assert not (tmp_path / "root").exists()


def test_evolve_rejects_model_batch_without_writes(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s.json").write_text('\u007b"session_id": "test", "turns": []\u007d')
    template = tmp_path / "template"
    template.write_text("{{SESSIONS}}")
    root = tmp_path / "candidates"
    with pytest.raises(RuntimeError):
        ev.evolve(
            sessions,
            root,
            template,
            runner=lambda _: (
                "~~~skill name=good\nok\n~~~\n~~~skill name=../outside\nbad\n~~~"
            ),
        )
    assert not root.exists()
    assert not (tmp_path / "outside").exists()


def test_final_symlink_swap_cannot_redirect_write(tmp_path, monkeypatch):
    from skillclaw import candidate_store as store

    root = tmp_path / "candidates"
    directory = root / "good"
    directory.mkdir(parents=True)
    outside = tmp_path / "trusted"
    outside.write_text("trusted")
    original = os.replace

    def swap(source, destination, **kwargs):
        (directory / "SKILL.md").symlink_to(outside)
        return original(source, destination, **kwargs)

    monkeypatch.setattr(store.os, "replace", swap)
    ev.write_candidates([_candidate("good")], root)
    assert outside.read_text() == "trusted"
    assert not (directory / "SKILL.md").is_symlink()
    assert (directory / "SKILL.md").read_text() == "candidate"


def test_relative_root_and_crlf_header(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = ev.parse_candidates("~~~skill name=good\r\nbody\r\n~~~")
    assert ev.write_candidates(candidates, "relative") == ["good"]
    assert (tmp_path / "relative/good/SKILL.md").read_bytes() == b"body\r\n"


def test_trusted_parent_symlink_dotdot_keeps_filesystem_meaning(tmp_path):
    child = tmp_path / "actual" / "child"
    child.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(child, target_is_directory=True)
    ev.write_candidates([_candidate("good")], alias / ".." / "candidates")
    assert (tmp_path / "actual/candidates/good/SKILL.md").read_text() == "candidate"
    assert not (tmp_path / "candidates").exists()


def test_update_preserves_private_permissions(tmp_path):
    root = tmp_path / "candidates"
    ev.write_candidates([_candidate("good", "old")], root)
    target = root / "good/SKILL.md"
    target.chmod(0o600)
    ev.write_candidates([_candidate("good", "new")], root)
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.read_text() == "new"
