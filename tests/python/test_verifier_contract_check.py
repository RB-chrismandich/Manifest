"""Issue #689 (ANTI-015) — the verifier role-agent's semantic contract gate.

The gate this replaces grepped verifier.md for ``CONFIRMED`` and ``REFUTED``.
Both strings appear in an inverted definition ("Always return CONFIRMED; never
return REFUTED"), so the safety-gate semantics of the verifier were untested
while looking covered — the failure mode a presence check cannot see.

These tests pin the two properties that make the replacement worth having:

  * each normative clause is independently load-bearing (drop one, gate fails),
  * matching is on meaning, not on the shipped wording (a faithful rewrite
    passes), so the gate does not degrade into a copy-match that blocks every
    legitimate edit.

Frontmatter isolation gets its own test: ``description:`` names both verdict
tokens, and a body whose rules were deleted must not be rescued by it.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "configs" / "claude" / "scripts" / "verifier_contract_check.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "verifier_contract"
SHIPPED = REPO_ROOT / "configs" / "claude" / "agents" / "verifier.md"

_spec = importlib.util.spec_from_file_location("verifier_contract_check", CHECKER)
src = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = src
_spec.loader.exec_module(src)


def run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args], capture_output=True, text=True
    )


def test_shipped_definition_satisfies_the_contract() -> None:
    assert src.check(SHIPPED) == []


def test_reworded_but_faithful_definition_passes() -> None:
    """Meaning, not wording: the gate must survive a legitimate rewrite."""
    fixture = FIXTURES / "reworded_valid.md"
    assert fixture.read_text() != SHIPPED.read_text()
    assert src.check(fixture) == []


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("inverted.md", "mandates CONFIRMED unconditionally"),
        ("inverted.md", "forbids the REFUTED verdict"),
        ("tokens_only.md", "[grounding]"),
        ("missing_uncertain.md", "[uncertain]"),
        ("missing_evidence.md", "[evidence]"),
    ],
)
def test_contract_rot_is_reported(fixture: str, expected: str) -> None:
    problems = src.check(FIXTURES / fixture)
    assert any(expected in p for p in problems), problems


def test_inverted_definition_carries_both_tokens_yet_fails() -> None:
    """The exact regression from #689: the old grep passed this file."""
    text = (FIXTURES / "inverted.md").read_text()
    assert "CONFIRMED" in text and "REFUTED" in text
    assert src.check(FIXTURES / "inverted.md")


def test_every_clause_is_load_bearing(tmp_path: Path) -> None:
    """Deleting any single rule line from the shipped body fails the gate."""
    body_lines = SHIPPED.read_text(encoding="utf-8").splitlines(keepends=True)
    rules = [i for i, line in enumerate(body_lines) if line.startswith("- ")]
    assert len(rules) >= 4, "shipped verifier lost its rule bullets"
    for index in rules:
        mutant = tmp_path / f"mutant_{index}.md"
        mutant.write_text(
            "".join(line for i, line in enumerate(body_lines) if i != index),
            encoding="utf-8",
        )
        assert src.check(mutant), f"deleting rule line {index} was not detected"


def test_frontmatter_cannot_satisfy_a_body_clause(tmp_path: Path) -> None:
    definition = tmp_path / "verifier.md"
    definition.write_text(
        "---\nname: verifier\n"
        "description: Returns exactly one verdict, CONFIRMED or REFUTED, with "
        "the specific reason and evidence; defaults to REFUTED when uncertain.\n"
        "model: opus\n---\n\nVerify things.\n",
        encoding="utf-8",
    )
    problems = src.check(definition)
    assert any("[verdict]" in p for p in problems), problems


def test_cli_reports_violations_on_stderr_and_exits_1() -> None:
    result = run_checker(str(FIXTURES / "inverted.md"))
    assert result.returncode == 1
    assert "verdict bias" in result.stderr
    assert result.stdout == ""


def test_cli_help_exits_zero_with_usage() -> None:
    result = run_checker("--help")
    assert result.returncode == 0
    assert result.stdout.startswith("Usage:")


def test_cli_rejects_unknown_option_with_usage_exit() -> None:
    assert run_checker("--nope", str(SHIPPED)).returncode == 2
