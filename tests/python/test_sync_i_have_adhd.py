from pathlib import Path

import pytest

from tools.sync_i_have_adhd import (
    GenerationError,
    drifted_files,
    generate,
    generated_files,
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
