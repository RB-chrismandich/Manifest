"""T1.3 (spec 674) — name-matching edge cases for the cross-skill gate.

Split from ``test_skill_reference_check.py``, which reached its 500-line
constitution ceiling. That file covers the tiers, the ratchet and the registry;
this one covers how a skill NAME is recognised in text.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "configs" / "claude" / "scripts" / "skill_reference_check.py"


def write_skill(root: Path, name: str, body: str) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: fixture for {name}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args], capture_output=True, text=True
    )


@pytest.fixture()
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


# --- case variants ---------------------------------------------------------
# Headings are routinely title-cased ("## PR-Review"), and a case-sensitive
# matcher sees nothing there -- not even a warning. Hyphenated names are matched
# case-insensitively because no ordinary English phrase looks like `pr-review`.


@pytest.mark.parametrize(
    "written", ["PR-Review", "Pr-Review", "PR-REVIEW", "pr-Review"]
)
def test_case_variants_of_a_hyphenated_name_are_caught(skills: Path, written: str):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", f"## {written}\n\nRelated but different.")

    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["warning_count"] == 1, f"{written} not matched: {payload}"


def test_case_variant_on_a_dispatch_line_blocks(skills: Path):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", "Then run PR-Review to finish.")
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 1, payload


# --- and the reason single words stay case-sensitive ------------------------
# The catalog names help and remotion carry no hyphen. `help`
# is an ordinary English word, and matching "Help" case-insensitively would fire
# on any sentence that begins with it. A gate that cries wolf gets switched off.


def test_capitalised_ordinary_word_is_not_a_false_positive(skills: Path):
    write_skill(skills, "help", "I list commands.")
    write_skill(skills, "repo-clean", "Help is available in the README.")
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["warning_count"] == 0, (
        f"false positive on ordinary English: {payload}"
    )


def test_exact_case_single_word_still_matches(skills: Path):
    write_skill(skills, "help", "I list commands.")
    write_skill(skills, "repo-clean", "See also `help` for the catalog.")
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["warning_count"] == 1, payload


def test_a_skills_own_title_cased_name_is_still_a_self_reference(skills: Path):
    """Case-folding the matcher without folding the self-reference test made a
    skill's own heading look like a cross-reference.

    Caught on the real tree: `upload-to-stitch/SKILL.md:12` opens with
    `# Upload-to-Stitch`, which the folded matcher saw as a reference to a
    DIFFERENT skill because `"Upload-to-Stitch" != "upload-to-stitch"`.
    """
    write_skill(skills, "upload-to-stitch", "# Upload-to-Stitch\n\nI upload things.")
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["warning_count"] == 0, (
        f"self-reference reported as cross-skill: {payload}"
    )
    assert payload["blocking_count"] == 0, payload


# --- ceiling slack ---------------------------------------------------------
# A ratchet nobody tightens is a ratchet at its loosest setting forever.


def test_below_ceiling_reports_the_lower_value(skills: Path, tmp_path: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "issue-dev-auto", "Run `/project-verify`.")

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"warning_total": 9, "blocking_total": 5}), encoding="utf-8"
    )

    result = run_checker("--roots", str(skills), "--baseline", str(baseline))
    assert result.returncode == 0
    # It must name the value to ratchet DOWN to, not merely restate the ceiling.
    assert "1" in result.stderr and "5" in result.stderr
    assert "lower" in result.stderr.lower() or "tighten" in result.stderr.lower()
