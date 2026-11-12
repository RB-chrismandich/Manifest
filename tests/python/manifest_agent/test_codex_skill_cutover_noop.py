from pathlib import Path

from manifest_agent.codex_skill_cutover import (
    inspect_codex_skill_source,
    prepare_codex_skill_cutover,
)


def test_empty_codex_skills_directory_is_a_noop(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    skills = home / ".codex/skills"
    skills.mkdir(parents=True)

    state = inspect_codex_skill_source(home, source)
    entry = prepare_codex_skill_cutover(home, source)

    assert state.kind == "user-managed"
    assert entry.previous_checksum is None
    assert list(skills.iterdir()) == []


def test_populated_codex_skills_directory_is_a_noop(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    skills = home / ".codex/skills"
    system = home / ".manifest/codex-system"
    (system / ".system").mkdir(parents=True)
    skills.mkdir(parents=True)
    (skills / ".system").symlink_to(system / ".system")
    skill = skills / "my-skill/SKILL.md"
    skill.parent.mkdir()
    contents = b"User skill bytes\x00\n"
    skill.write_bytes(contents)

    entry = prepare_codex_skill_cutover(home, source)

    assert entry.previous_checksum is None
    assert skill.read_bytes() == contents
    assert sorted(path.name for path in skills.iterdir()) == [".system", "my-skill"]
    assert not (home / ".codex/.skills.manifest-cutover").exists()
    assert not (home / ".codex/.skills.manifest-cutover.pending").exists()


def test_missing_codex_skills_path_is_a_noop(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    skills = home / ".codex/skills"

    entry = prepare_codex_skill_cutover(home, source)

    assert entry.previous_checksum is None
    assert not skills.exists()
    assert not skills.is_symlink()
