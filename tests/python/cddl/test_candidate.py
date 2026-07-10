"""US1 — candidate grammar, write confinement, atomic apply (T014, FR-017).

Contract: specs/482-critic-dev-loop/contracts/candidate-format.md fixture list.
"""

import pytest
from cddl.candidate import apply_candidate, parse_candidate, serialize_candidate


def wrap(*blocks, notes="Here is the change.\n"):
    return notes + "\n" + "\n".join(blocks)


def fblock(path, content="content\n", kind="cddl-file"):
    return f"```{kind} {path}\n{content}```"


# --- confinement rejections (whole candidate, zero writes) ---


@pytest.mark.parametrize(
    "path",
    [
        "../escape.txt",  # upward traversal
        "sub/../../escape.txt",  # embedded traversal
        "/etc/x",  # absolute
        ".git/hooks/x",  # git internals
        "bad path.txt",  # space in path (v1 grammar)
        "foo\\..\\bar.txt",  # backslash pseudo-traversal (v1 grammar)
    ],
)
def test_rejected_paths(fixture_repo, path):
    cand = parse_candidate(wrap(fblock(path)), fixture_repo)
    assert not cand.ok
    assert cand.deficiency
    before = (fixture_repo / path.lstrip("/")).exists()
    assert not before


def test_symlink_parent_escape_rejected(fixture_repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (fixture_repo / "sneaky").symlink_to(outside)
    cand = parse_candidate(wrap(fblock("sneaky/evil.txt")), fixture_repo)
    assert not cand.ok
    assert (
        "escape" in cand.deficiency.lower() or "repository" in cand.deficiency.lower()
    )
    assert not (outside / "evil.txt").exists()


def test_all_or_nothing_one_bad_path_rejects_all(fixture_repo):
    raw = wrap(fblock("good.txt", "fine\n"), fblock("../bad.txt"))
    cand = parse_candidate(raw, fixture_repo)
    assert not cand.ok
    assert not (fixture_repo / "good.txt").exists()


def test_zero_blocks_is_no_candidate(fixture_repo):
    cand = parse_candidate("I could not produce a change this round.", fixture_repo)
    assert not cand.ok
    assert "no-candidate" in cand.deficiency


def test_nonempty_delete_body_rejected(fixture_repo):
    raw = wrap(fblock("README.md", "leftover\n", kind="cddl-delete"))
    cand = parse_candidate(raw, fixture_repo)
    assert not cand.ok


# --- happy paths ---


def test_multi_file_happy_path_and_written_paths(fixture_repo):
    raw = wrap(
        fblock("pkg/mod.py", "print('hi')\n"),
        fblock("docs/note.md", "note\n"),
    )
    cand = parse_candidate(raw, fixture_repo)
    assert cand.ok
    assert [f.path for f in cand.files] == ["pkg/mod.py", "docs/note.md"]
    written = apply_candidate(cand, fixture_repo)
    assert written == ["pkg/mod.py", "docs/note.md"]
    assert (fixture_repo / "pkg" / "mod.py").read_text() == "print('hi')\n"
    assert (fixture_repo / "docs" / "note.md").read_text() == "note\n"
    leftovers = list(fixture_repo.rglob("*.cddl-tmp"))
    assert leftovers == []


def test_empty_body_creates_empty_file(fixture_repo):
    cand = parse_candidate(wrap(fblock("empty.txt", "")), fixture_repo)
    assert cand.ok
    apply_candidate(cand, fixture_repo)
    assert (fixture_repo / "empty.txt").read_text() == ""


def test_delete_block_removes_file(fixture_repo):
    target = fixture_repo / "obsolete.txt"
    target.write_text("old\n")
    cand = parse_candidate(
        wrap(fblock("obsolete.txt", "", kind="cddl-delete")), fixture_repo
    )
    assert cand.ok
    written = apply_candidate(cand, fixture_repo)
    assert written == ["obsolete.txt"]
    assert not target.exists()


def test_prose_notes_retained(fixture_repo):
    raw = wrap(fblock("a.txt", "x\n"), notes="Rationale: minimal change.\n")
    cand = parse_candidate(raw, fixture_repo)
    assert "Rationale" in cand.notes


def test_notes_exclude_block_bodies(fixture_repo):
    # Contract: "prose OUTSIDE blocks is retained as notes" — file content must
    # never leak into notes (it would be duplicated into critic prompts).
    raw = wrap(fblock("a.txt", "secret-body\n"), notes="Only this is prose.\n")
    cand = parse_candidate(raw, fixture_repo)
    assert "Only this is prose." in cand.notes
    assert "secret-body" not in cand.notes
    assert "```" not in cand.notes


def test_overwrite_existing_file_is_atomic(fixture_repo):
    (fixture_repo / "README.md").write_text("original\n")
    cand = parse_candidate(wrap(fblock("README.md", "replaced\n")), fixture_repo)
    apply_candidate(cand, fixture_repo)
    assert (fixture_repo / "README.md").read_text() == "replaced\n"


# --- stall serialization (loop compares byte-identical candidates) ---


def test_serialize_identical_candidates_equal(fixture_repo):
    a = parse_candidate(wrap(fblock("x.py", "same\n")), fixture_repo)
    b = parse_candidate(
        wrap(fblock("x.py", "same\n"), notes="different prose\n"), fixture_repo
    )
    assert serialize_candidate(a) == serialize_candidate(b)


def test_serialize_different_candidates_differ(fixture_repo):
    a = parse_candidate(wrap(fblock("x.py", "one\n")), fixture_repo)
    b = parse_candidate(wrap(fblock("x.py", "two\n")), fixture_repo)
    assert serialize_candidate(a) != serialize_candidate(b)
