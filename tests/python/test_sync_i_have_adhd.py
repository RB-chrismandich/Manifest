import os
import sys
from pathlib import Path

import pytest

from tools.sync_i_have_adhd import (
    GenerationError,
    drifted_files,
    generate,
    generated_files,
    main,
)


def test_checked_in_guidance_matches_canonical_skill() -> None:
    bundle = Path.cwd() / "plugins/manifest-i-have-adhd"

    assert drifted_files(bundle) == ()


def test_generated_files_strip_skill_frontmatter(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    skill = bundle / "skills/i-have-adhd/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: i-have-adhd\n---\n\n# i-have-adhd\n", encoding="utf-8")

    generate(bundle)

    assert generated_files(bundle) == {
        Path("guidance/always-on.md"): b"# i-have-adhd\n",
        Path("devin/global-rule.md"): b"# i-have-adhd\n",
    }
    assert drifted_files(bundle) == ()


def test_guidance_only_drift_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    skill = bundle / "skills/i-have-adhd/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# i-have-adhd\n", encoding="utf-8")
    generate(bundle)
    (bundle / "guidance/always-on.md").write_text("drifted\n", encoding="utf-8")

    assert drifted_files(bundle) == (Path("guidance/always-on.md"),)


def test_unterminated_skill_frontmatter_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    skill = bundle / "skills/i-have-adhd/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: i-have-adhd\n", encoding="utf-8")

    with pytest.raises(GenerationError, match="unterminated frontmatter"):
        generate(bundle)


def _bundle_with_guidance(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    skill = bundle / "skills/i-have-adhd/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# i-have-adhd\n", encoding="utf-8")
    generate(bundle)
    return bundle


def test_symlinked_guidance_is_drift_even_with_matching_bytes(tmp_path: Path) -> None:
    bundle = _bundle_with_guidance(tmp_path)
    target = bundle / "guidance/always-on.md"
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(elsewhere)

    assert drifted_files(bundle) == (Path("guidance/always-on.md"),)

    generate(bundle)

    assert not target.is_symlink()
    assert drifted_files(bundle) == ()


def test_malformed_utf8_skill_is_a_generation_error(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    skill = bundle / "skills/i-have-adhd/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(b"# i-have-adhd \xff\xfe\n")

    with pytest.raises(GenerationError, match="not valid UTF-8"):
        drifted_files(bundle)


def test_unreadable_guidance_is_a_generation_error(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read mode-000 files")
    bundle = _bundle_with_guidance(tmp_path)
    target = bundle / "guidance/always-on.md"
    target.chmod(0)
    try:
        with pytest.raises(GenerationError, match="unable to read generated file"):
            drifted_files(bundle)
    finally:
        target.chmod(0o644)


def test_cli_reports_malformed_utf8_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = tmp_path / "bundle"
    skill = bundle / "skills/i-have-adhd/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(b"\xff\n")
    monkeypatch.setattr(
        sys, "argv", ["sync_i_have_adhd.py", "--bundle", str(bundle), "--check"]
    )

    assert main() == 2
    assert "not valid UTF-8" in capsys.readouterr().out
