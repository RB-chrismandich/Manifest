"""T1.1 (spec 674) — the cross-skill reference resolver.

Why a resolver rather than a sweep:

There is NO string that works in both eras. A bare `/project-verify` resolves
today and dies after the cutover; a qualified `/manifest-code-quality:project-verify`
resolves after and is an Unknown command today. Verified: nothing in the deploy
path substitutes anything into a SKILL.md -- `deploy_home_skills` is rsync with
a cp fallback -- so a token written into a body today would reach the model
verbatim and break a working skill for a future benefit.

So the source carries a token, and whatever materialises the tree expands it for
the era it is materialising into. This module is that expansion, landed and
tested in Phase 1 so Phase 3's mirror wires it rather than designs it.

Token spelling is `[[skill:<name>]]`, not `{{...}}`: three skill bodies already
contain GitHub Actions `${{ }}` expressions, and a gate that has to tell those
apart from a Manifest token is a gate that will eventually get it wrong.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOLVER = REPO_ROOT / "configs" / "claude" / "scripts" / "skill_ref.py"
REGISTRY = REPO_ROOT / "configs" / "claude" / "config" / "skill_policies.yml"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RESOLVER), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_help_exits_zero():
    assert run("--help").returncode == 0


def test_bare_mode_emits_the_unqualified_command():
    out = run(
        "--mode",
        "bare",
        "--registry",
        str(REGISTRY),
        stdin="Run [[skill:project-verify]].",
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "Run /project-verify."


def test_qualified_mode_emits_the_bundle_scoped_command():
    out = run(
        "--mode",
        "qualified",
        "--registry",
        str(REGISTRY),
        stdin="Run [[skill:project-verify]].",
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "Run /manifest-code-quality:project-verify."


@pytest.mark.parametrize(
    ("skill", "bundle"),
    [
        ("git-commit", "manifest-forge"),
        ("graphify", "manifest-graphify"),
        ("upload-to-stitch", "stitch-design"),
        ("ci-setup", "manifest-ops"),
        ("ci-harden-workflow", "manifest-security"),
    ],
)
def test_every_bundle_resolves(skill: str, bundle: str):
    out = run(
        "--mode", "qualified", "--registry", str(REGISTRY), stdin=f"[[skill:{skill}]]"
    )
    assert out.stdout.strip() == f"/{bundle}:{skill}"


def test_unknown_skill_fails_loudly(tmp_path: Path):
    """A typo'd token must never pass through as literal text.

    Silently emitting `[[skill:projct-verify]]` into a shipped body is the same
    silent failure the whole naming workstream exists to remove.
    """
    out = run(
        "--mode",
        "bare",
        "--registry",
        str(REGISTRY),
        stdin="Run [[skill:projct-verify]].",
    )
    assert out.returncode != 0
    assert "projct-verify" in out.stderr


def test_github_actions_expressions_are_untouched():
    """Three skill bodies carry ${{ }}; the token must not collide with them."""
    body = "uses: ${{ github.event.inputs.x }} and ${{ matrix.os }}"
    out = run("--mode", "qualified", "--registry", str(REGISTRY), stdin=body)
    assert out.returncode == 0
    assert out.stdout.strip() == body


def test_text_without_tokens_round_trips_byte_for_byte():
    body = "# Heading\n\nSome prose with `/not-a-token` and a [link](x).\n"
    out = run("--mode", "bare", "--registry", str(REGISTRY), stdin=body)
    assert out.stdout == body


def test_missing_registry_fails_closed(tmp_path: Path):
    out = run(
        "--mode",
        "qualified",
        "--registry",
        str(tmp_path / "nope.yml"),
        stdin="[[skill:git-commit]]",
    )
    assert out.returncode != 0


def test_check_mode_reports_tokens_without_rewriting():
    out = run(
        "--mode",
        "check",
        "--registry",
        str(REGISTRY),
        stdin="a [[skill:git-commit]] b [[skill:pr-review]]",
    )
    assert out.returncode == 0
    assert "git-commit" in out.stdout and "pr-review" in out.stdout
