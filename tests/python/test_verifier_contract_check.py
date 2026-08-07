"""Issue #689 (ANTI-015) — the verifier role-agent's contract gate.

The gate this replaces grepped verifier.md for ``CONFIRMED`` and ``REFUTED``.
Both strings appear in an inverted definition ("Always return CONFIRMED; never
return REFUTED"), so the safety-gate semantics were untested while looking
covered — the failure a presence check cannot see.

Two adversarial review rounds then walked through successive keyword
heuristics; every fixture used here is one of those demonstrated bypasses. The
gate is now an allowlist over canonical clauses, so these tests pin:

  * the shipped Claude and Cursor definitions satisfy it,
  * each canonical clause is load-bearing (delete one, gate fails),
  * negation, suppression, contradiction, and appended overrides fail even
    though they name the right words in the right places,
  * an inverted CONTRACT is rejected before any definition is read, so the
    allowlist cannot be laundered through its own data,
  * a deliberate, matched edit of contract + definition passes — the escape
    hatch that keeps the gate from freezing the file forever.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "configs" / "claude" / "scripts" / "verifier_contract_check.py"
CONTRACT = REPO_ROOT / "configs" / "claude" / "config" / "verifier_contract.json"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "verifier_contract"
SHIPPED = REPO_ROOT / "configs" / "claude" / "agents" / "verifier.md"
CURSOR = REPO_ROOT / "configs" / "cursor" / "agents" / "verifier.md"

_spec = importlib.util.spec_from_file_location("verifier_contract_check", CHECKER)
src = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = src
_spec.loader.exec_module(src)

CLAUSES = src.load_contract(CONTRACT)


def run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args], capture_output=True, text=True
    )


@pytest.mark.parametrize("definition", [SHIPPED, CURSOR], ids=["claude", "cursor"])
def test_shipped_definitions_match_the_contract(definition: Path) -> None:
    assert src.check(definition, CLAUSES) == []


def test_shipped_contract_is_not_itself_biased() -> None:
    assert src.check_contract(CLAUSES) == []


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        # The original #689 regression: both tokens present, contract gutted.
        ("inverted.md", "[verdict]"),
        ("tokens_only.md", "[grounding]"),
        ("missing_uncertain.md", "[uncertain]"),
        ("missing_evidence.md", "[verdict]"),
        # Review round 1: clause-scoped co-occurrence is not sentence agreement.
        ("contradictory_uncertain.md", "non-canonical verdict sentence"),
        ("late_confirmed_override.md", "non-canonical verdict sentence"),
        # Review round 2: polarity and suppression are not pattern-decidable.
        ("avoid_refuted.md", "[uncertain]"),
        ("negated_evidence.md", "[verdict]"),
        ("suppress_refuted_append.md", "non-canonical verdict sentence"),
        ("hollow_condition_append.md", "non-canonical verdict sentence"),
    ],
)
def test_every_known_bypass_now_fails(fixture: str, expected: str) -> None:
    problems = src.check(FIXTURES / fixture, CLAUSES)
    assert any(expected in p for p in problems), problems


def test_every_clause_is_load_bearing(tmp_path: Path) -> None:
    """Deleting any single rule line from the shipped body fails the gate."""
    lines = SHIPPED.read_text(encoding="utf-8").splitlines(keepends=True)
    rules = [i for i, line in enumerate(lines) if line.startswith("- ")]
    assert len(rules) == len(CLAUSES), "rule bullets and contract clauses diverged"
    for index in rules:
        mutant = tmp_path / f"mutant_{index}.md"
        mutant.write_text(
            "".join(line for i, line in enumerate(lines) if i != index),
            encoding="utf-8",
        )
        assert src.check(mutant, CLAUSES), f"deleting rule line {index} went unseen"


def test_frontmatter_cannot_satisfy_the_contract(tmp_path: Path) -> None:
    """description: names both verdicts; a gutted body must not inherit them."""
    definition = tmp_path / "verifier.md"
    definition.write_text(
        "---\nname: verifier\n"
        "description: Returns exactly one verdict, CONFIRMED or REFUTED, with "
        "the specific reason and evidence; defaults to REFUTED when uncertain.\n"
        "model: opus\n---\n\nVerify things.\n",
        encoding="utf-8",
    )
    assert len(src.check(definition, CLAUSES)) == len(CLAUSES)


def test_inverted_contract_is_rejected_before_any_definition() -> None:
    """The allowlist must not be laundered by editing its own data."""
    result = run_checker(
        "--contract", str(FIXTURES / "inverted_contract.json"), str(SHIPPED)
    )
    assert result.returncode == 1
    assert "is itself biased" in result.stderr
    assert result.stdout == ""  # never reports OK on a poisoned contract


def test_matched_contract_and_definition_edit_passes(tmp_path: Path) -> None:
    """The escape hatch: rewording is allowed when the contract moves with it."""
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "clauses": [
                    {
                        "id": "verdict",
                        "text": "Emit exactly one verdict, CONFIRMED or REFUTED.",
                    },
                    {
                        "id": "uncertain",
                        "text": "If unsure, the verdict is REFUTED.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    definition = tmp_path / "verifier.md"
    definition.write_text(
        "---\nname: verifier\n---\n\n"
        "- Emit **exactly one verdict**, `CONFIRMED` or `REFUTED`.\n"
        "- If unsure, the verdict is `REFUTED`.\n",
        encoding="utf-8",
    )
    assert src.check(definition, src.load_contract(contract)) == []


def test_cli_reports_violations_on_stderr_and_exits_1() -> None:
    result = run_checker(str(FIXTURES / "inverted.md"))
    assert result.returncode == 1
    assert result.stderr
    assert result.stdout == ""


def test_cli_help_exits_zero_with_usage() -> None:
    result = run_checker("--help")
    assert result.returncode == 0
    assert result.stdout.startswith("Usage:")


@pytest.mark.parametrize(
    "args",
    [("--nope", str(SHIPPED)), ("--contract",), (str(FIXTURES / "x.md"),)],
    ids=["unknown-option", "dangling-contract", "missing-file"],
)
def test_cli_never_exits_zero_on_bad_input(args: tuple[str, ...]) -> None:
    assert run_checker(*args).returncode != 0
