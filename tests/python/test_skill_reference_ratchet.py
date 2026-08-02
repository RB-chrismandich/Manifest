"""T1.3 (spec 674) — ratchet and registry behaviour for the cross-skill gate.

Split from ``test_skill_reference_check.py`` at its 500-line constitution
ceiling, along a responsibility seam rather than at the midpoint: that file
covers WHICH references are found and how they are tiered, this one covers the
ceilings that decide whether findings fail the build.
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
    """Create a skill dir with realistic frontmatter."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: fixture for {name}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def run_checker(*args: str) -> subprocess.CompletedProcess:
    """Invoke the gate out-of-process, the way CI does."""
    return subprocess.run(
        [sys.executable, str(CHECKER), *args], capture_output=True, text=True
    )


@pytest.fixture()
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


def test_warning_over_baseline_fails(skills: Path, tmp_path: Path):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", "See also `pr-review` and again `pr-review`.")

    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"warning_total": 1}), encoding="utf-8")

    result = run_checker("--roots", str(skills), "--baseline", str(baseline), "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["warning_count"] == 2
    assert "ratchet" in result.stderr.lower() or "baseline" in result.stderr.lower()


def test_blocking_without_a_baseline_always_fails(skills: Path):
    """Default posture: any blocking reference fails. A baseline is opt-in."""
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "issue-dev-auto", "Run `/project-verify`.")
    result = run_checker("--roots", str(skills), "--json")
    assert result.returncode == 1


def test_blocking_at_baseline_passes(skills: Path, tmp_path: Path):
    """The blocking tier ratchets too, and here is why.

    Wiring this gate into CI while 35 pre-existing blocking references sat in
    the tree turned every PR red for a condition the PR did not cause. T1.1 is
    the remediation; until it lands the gate holds the line at the measured
    count instead of blocking unrelated work. Any INCREASE still fails.
    """
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "issue-dev-auto", "Run `/project-verify`.")

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"warning_total": 0, "blocking_total": 1}), encoding="utf-8"
    )

    result = run_checker("--roots", str(skills), "--baseline", str(baseline), "--json")
    assert result.returncode == 0, result.stdout


def test_blocking_above_baseline_fails(skills: Path, tmp_path: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(
        skills, "issue-dev-auto", "Run `/project-verify` then `/project-verify` again."
    )

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"warning_total": 0, "blocking_total": 1}), encoding="utf-8"
    )

    result = run_checker("--roots", str(skills), "--baseline", str(baseline), "--json")
    assert result.returncode == 1
    assert "blocking" in result.stderr.lower()


def test_blocking_swap_at_the_same_count_is_caught(skills: Path, tmp_path: Path):
    """The blind spot every count-only ratchet has.

    Remove one blocking reference, add a different one, and the total is
    unchanged — so a count ceiling passes a tree that gained a brand new
    silent-failure site. The baseline therefore pins the SET of sites, not just
    how many there are.
    """
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "pr-review", "I review.")
    write_skill(skills, "issue-dev-auto", "Run `/project-verify`.")

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "warning_total": 0,
                "blocking_total": 1,
                "blocking_sites": ["issue-dev-auto -> project-verify"],
            }
        ),
        encoding="utf-8",
    )
    assert (
        run_checker("--roots", str(skills), "--baseline", str(baseline)).returncode == 0
    )

    # Same count, different site.
    (skills / "issue-dev-auto" / "SKILL.md").write_text(
        "---\nname: issue-dev-auto\ndescription: x\n---\n\nRun `/pr-review`.\n",
        encoding="utf-8",
    )
    result = run_checker("--roots", str(skills), "--baseline", str(baseline))
    assert result.returncode == 1, "a swap at the same count slipped through"
    assert "pr-review" in result.stderr


def test_blocking_sites_absent_from_baseline_falls_back_to_the_count(
    skills: Path, tmp_path: Path
):
    """A baseline written before site-pinning existed must keep working."""
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "issue-dev-auto", "Run `/project-verify`.")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"warning_total": 0, "blocking_total": 1}), encoding="utf-8"
    )
    assert (
        run_checker("--roots", str(skills), "--baseline", str(baseline)).returncode == 0
    )


def test_warning_under_baseline_passes_and_reports_slack(skills: Path, tmp_path: Path):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", "See also `pr-review`.")

    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"warning_total": 5}), encoding="utf-8")

    result = run_checker("--roots", str(skills), "--baseline", str(baseline), "--json")
    assert result.returncode == 0, result.stdout


def test_registry_mismatch_fails(skills: Path, tmp_path: Path):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", "Body.")

    registry = tmp_path / "skill_policies.yml"
    registry.write_text("expected_total: 99\n", encoding="utf-8")

    result = run_checker("--roots", str(skills), "--registry", str(registry), "--json")
    assert result.returncode == 1
    assert "99" in result.stderr and "2" in result.stderr


def test_registry_match_passes(skills: Path, tmp_path: Path):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", "Body.")

    registry = tmp_path / "skill_policies.yml"
    registry.write_text("expected_total: 2\n", encoding="utf-8")

    result = run_checker("--roots", str(skills), "--registry", str(registry), "--json")
    assert result.returncode == 0, result.stdout


def test_real_registry_matches_the_tree():
    """The committed integer must equal the catalog it guards, today."""
    registry = REPO_ROOT / "configs" / "claude" / "config" / "skill_policies.yml"
    roots = ":".join(
        str(path / "skills")
        for path in sorted((REPO_ROOT / "plugins").iterdir())
        if (path / "skills").is_dir()
    )
    result = run_checker(
        "--roots",
        roots,
        "--registry",
        str(registry),
        "--baseline",
        str(
            REPO_ROOT
            / "configs"
            / "claude"
            / "config"
            / "skill_reference_baseline.json"
        ),
        "--json",
    )
    assert "expected_total" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
