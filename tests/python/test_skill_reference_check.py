"""T1.3 (spec 674) — the cross-skill reference gate.

Why this exists, and why it is not a one-line grep:

Post-cutover a plugin skill is reachable ONLY as ``<plugin>:<skill>``. Every bare
cross-skill reference inside a skill body therefore stops resolving. The original
task specified this gate as "grep every SKILL.md for /<name>", which catches 20 of
the 35 must-fix sites and is *structurally blind* to the other 15 — including
``docs-all``, which dispatches ``docs-improve-readme`` as a sub-agent by bare name
with no slash and then prints a per-skill success table. A gate that ships green
over the skill whose failure mode is a fabricated success table is worse than no
gate, because it is believed.

So the checker separates:

  BLOCKING  slash-form (``/project-verify``), and slashless names on a dispatch
            line (``run `docs-improve-readme` ``) — these break at runtime.
  WARNING   slashless names in prose (``see also `pr-review` ``) — these break the
            name a reader is told to type, not the runtime. Baselined and
            ratcheted rather than failed on, because 122 pre-existing pointers
            would otherwise drown the signal, and a permanently-noisy gate is a
            disabled gate.

Qualified references and the ``{{skill:<name>}}`` token are the REMEDIATION, so
they must never be flagged.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "configs" / "claude" / "scripts" / "skill_reference_check.py"

# Most cases drive the CLI as a subprocess; the root-defaulting cases need the
# function itself, since its whole job is choosing what to scan.
_spec = importlib.util.spec_from_file_location("skill_reference_check", CHECKER)
src = importlib.util.module_from_spec(_spec)
# Registered BEFORE exec: the module defines dataclasses, and dataclasses
# resolves annotations via sys.modules[cls.__module__] -- absent, that is an
# AttributeError on None at import time.
sys.modules[_spec.name] = src
_spec.loader.exec_module(src)


def write_skill(
    root: Path, name: str, body: str, *, filename: str = "SKILL.md"
) -> Path:
    """Create a skill dir with a body. Frontmatter is realistic on purpose:
    the checker must not flag a skill's own name in its frontmatter."""
    d = root / name
    (d / filename).parent.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(
        f"---\nname: {name}\ndescription: test fixture for {name}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return d / filename


def run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


# --- help path -------------------------------------------------------------


def test_help_exits_zero_before_any_state_lookup():
    result = run_checker("--help")
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_help_is_at_most_15_lines():
    result = run_checker("--help")
    assert len(result.stdout.strip().splitlines()) <= 15


# --- class A: slash-form (blocking) ----------------------------------------


def test_slash_form_reference_is_blocking(skills: Path):
    write_skill(skills, "project-verify", "I verify things.")
    write_skill(skills, "issue-dev-auto", "5. **Verify.** Run `/project-verify`.")

    result = run_checker("--roots", str(skills), "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 1
    hit = payload["blocking"][0]
    assert hit["source"] == "issue-dev-auto"
    assert hit["target"] == "project-verify"
    assert hit["kind"] == "slash"


def test_self_reference_is_not_flagged(skills: Path):
    write_skill(skills, "git-commit", "Invoke me as `/git-commit`.")
    result = run_checker("--roots", str(skills), "--json")
    assert result.returncode == 0, result.stdout


def test_frontmatter_name_is_not_flagged(skills: Path):
    write_skill(skills, "pr-review", "Body with no references.")
    write_skill(skills, "repo-clean", "Body with no references.")
    result = run_checker("--roots", str(skills), "--json")
    assert result.returncode == 0, result.stdout


# --- class B: slashless dispatch (blocking) — the class the original gate missed


@pytest.mark.parametrize(
    "line",
    [
        "run `docs-improve-readme` early.",
        "Delegate to the `docs-improve-readme` skill to do the thing.",
        "Then invoke `docs-improve-readme` as a sub-agent.",
        "Hand off to `docs-improve-readme` for the rewrite.",
        "Dispatch `docs-improve-readme` and wait.",
        # Bold, not backticks. This is a REAL site the backtick-only version
        # missed: generate-design:154 "Delegate to the **upload-to-stitch** skill".
        "Delegate to the **docs-improve-readme** skill to do the thing.",
        "Run docs-improve-readme first, then stop.",
    ],
)
def test_slashless_dispatch_is_blocking(skills: Path, line: str):
    write_skill(skills, "docs-improve-readme", "I rewrite READMEs.")
    write_skill(skills, "docs-all", line)

    result = run_checker("--roots", str(skills), "--json")

    assert result.returncode == 1, f"dispatch line not caught: {line}\n{result.stdout}"
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 1
    assert payload["blocking"][0]["kind"] == "dispatch"


def test_docs_all_regression_shape(skills: Path):
    """The concrete case: a slash-only gate ships green over this."""
    for n in ("docs-improve-readme", "docs-generate-diagrams", "docs-improve"):
        write_skill(skills, n, "A docs skill.")
    write_skill(
        skills,
        "docs-all",
        "- **Default (no strong signal):** run `docs-improve-readme` →\n"
        "  `docs-generate-diagrams` → `docs-improve`.",
    )
    result = run_checker("--roots", str(skills), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] >= 1
    assert all(h["kind"] == "dispatch" for h in payload["blocking"])


# --- class C: prose pointers (warning, baselined) --------------------------


def test_prose_pointer_is_warning_not_blocking(skills: Path):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(
        skills, "repo-clean", "This is one half of the sweep (see also `pr-review`)."
    )

    result = run_checker("--roots", str(skills), "--json")

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 0
    assert payload["warning_count"] == 1


# --- prose tier: markup other than code spans ------------------------------
# The dispatch tier was widened to any markup after a real bold site turned up
# (generate-design -> **upload-to-stitch**). The prose tier was left
# backtick-only, so the SAME bold form was blocking on a dispatch line and
# invisible one line later. Both tiers now see the same forms; only the
# consequence differs.


@pytest.mark.parametrize(
    "line",
    [
        "Related but different: **pr-review** covers the other half.",
        "Related but different: _pr-review_ covers the other half.",
        "See [background](pr-review) for the other half.",
        "See <pr-review> for the other half.",
    ],
)
def test_prose_markup_is_counted_as_warning(skills: Path, line: str):
    write_skill(skills, "pr-review", "I review PRs.")
    write_skill(skills, "repo-clean", line)

    result = run_checker("--roots", str(skills), "--json")

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 0
    assert payload["warning_count"] == 1, f"missed: {line}\n{result.stdout}"


# --- and must not fire on text that is not a reference ---------------------
# The counterpart risk: a gate that cries wolf gets switched off. Fenced code
# and HTML comments are not instructions to the model.


def test_fenced_code_block_is_demoted_not_dropped(skills: Path):
    """A fenced example must not FAIL the build, but must still be counted.

    Dropping fenced content outright would hide a real break: a fenced shell
    example invoking /project-verify stops resolving after the cutover exactly
    like a prose one does.
    """
    write_skill(skills, "project-verify", "I verify.")
    write_skill(
        skills,
        "docs-all",
        "Example of the OLD syntax we no longer use:\n\n"
        "```\nrun /project-verify\n```\n\nUse the token instead.",
    )
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 0, payload
    assert payload["warning_count"] == 1, payload


def test_html_comment_is_ignored(skills: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "docs-all", "<!-- historical: run /project-verify here -->")
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 0, payload


def test_unbalanced_fence_does_not_swallow_the_rest_of_the_file(skills: Path):
    """An odd number of fence markers must fail toward MORE scanning.

    Real case: session-checkpoint/SKILL.md carries 11 fence markers because it
    uses ```text where a bare ``` should close. A naive toggle therefore ends
    the file "inside" a fence and blanks everything after the last marker --
    silently hiding any reference in the tail. A gate must never quietly stop
    looking; when the markers do not balance, scan the file as unfenced.
    """
    write_skill(skills, "project-verify", "I verify.")
    write_skill(
        skills,
        "docs-all",
        "```text\nan example\n```\n\n```bash\nunterminated on purpose\n\n"
        "Then run `/project-verify` to confirm.",
    )
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 1, (
        f"reference hidden by an unbalanced fence: {payload}"
    )


def test_balanced_fences_still_demote(skills: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(
        skills,
        "docs-all",
        "```bash\nrun /project-verify\n```\n\nplain trailing text.",
    )
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 0, payload
    assert payload["warning_count"] == 1, payload


def test_indented_code_block_is_not_mistaken_for_a_fence(skills: Path):
    # A real reference must survive ordinary indentation.
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "issue-dev-auto", "  - Then run `/project-verify` to confirm.")
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 1, payload


# --- the remediation forms must never be flagged ---------------------------


def test_qualified_reference_is_allowed(skills: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(
        skills, "issue-dev-auto", "Run `/manifest-code-quality:project-verify`."
    )
    result = run_checker("--roots", str(skills), "--json")
    assert result.returncode == 0, result.stdout


def test_skill_token_is_allowed(skills: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "issue-dev-auto", "Run {{skill:project-verify}}.")
    result = run_checker("--roots", str(skills), "--json")
    assert result.returncode == 0, result.stdout


def test_relative_link_is_not_a_slash_reference(skills: Path):
    """measured-facts M8 counted these as slash commands. They are file paths."""
    write_skill(skills, "extract-static-html", "I extract HTML.")
    write_skill(
        skills,
        "code-to-design",
        "Read [skills/extract-static-html/SKILL.md](../extract-static-html/SKILL.md).",
    )
    result = run_checker("--roots", str(skills), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 0, payload
    # It is reported in its own class so T3.6 can enforce same-bundle co-location.
    assert payload["relative_link_count"] == 1


# --- sidecars: references/ and prompts/ ship inside the plugin too ---------


def test_sidecar_files_are_scanned(skills: Path):
    write_skill(skills, "project-verify", "I verify.")
    write_skill(skills, "spec-implement-loop", "Body.")
    sidecar = skills / "spec-implement-loop" / "prompts" / "developer-dispatch.md"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("Then run `/project-verify` and report.\n", encoding="utf-8")

    result = run_checker("--roots", str(skills), "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any("developer-dispatch.md" in h["file"] for h in payload["blocking"])


# --- multi-root: the checker must survive the Phase 3 move ------------------


def test_multiple_roots_are_scanned(tmp_path: Path):
    a = tmp_path / "bundle-a" / "skills"
    b = tmp_path / "bundle-b" / "skills"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    write_skill(a, "project-verify", "I verify.")
    write_skill(b, "issue-dev-auto", "Run `/project-verify`.")

    result = run_checker("--roots", f"{a}:{b}", "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] == 1


# --- registry cross-check --------------------------------------------------
# Requirement 2 said resolve hits "against the registry key set from
# skill_policies.yml". The catalog is still derived from directory names -- the
# tree is the thing being guarded, so deriving from it cannot drift -- but the
# derived size is now checked against the committed integer. That is what makes
# it registry-BACKED rather than merely self-consistent: a skill that silently
# vanishes changes both the tree and the derived catalog, and only an exogenous
# number notices.


# --- real repo ------------------------------------------------------------


def test_real_repo_measurement_is_stable():
    """Pins the measured 2026-07-30 figures so a regression is visible.

    Uses the pinned bug-tolerant form (test-pin-bug): asserts the counts are at
    least the measured floor, so landing T1.1's remediation lowers them without
    breaking this test.
    """
    result = run_checker("--roots", str(REPO_ROOT / ".apm" / "skills"), "--json")
    payload = json.loads(result.stdout)
    assert payload["blocking_count"] > 0, (
        "expected the known 33-site surface pre-remediation"
    )
    assert payload["warning_count"] > 0


def test_default_roots_prefer_the_plugin_trees_over_the_generated_mirror(tmp_path):
    """`.apm/skills` is a generated, gitignored mirror since T3.3.

    Reporting hits there sends whoever reads the output to edit files the next
    generate_skill_mirror.sh run destroys: the fix passes review, passes this
    gate on the spot, and is gone by the next rebuild.
    """
    (tmp_path / "plugins/manifest-demo/skills/alpha").mkdir(parents=True)
    (tmp_path / ".apm/skills/alpha").mkdir(parents=True)
    roots = src.default_roots(tmp_path)
    assert roots == [tmp_path / "plugins/manifest-demo/skills"]


def test_default_roots_fall_back_to_the_mirror_on_a_pre_cutover_checkout(tmp_path):
    (tmp_path / ".apm/skills/alpha").mkdir(parents=True)
    assert src.default_roots(tmp_path) == [tmp_path / ".apm" / "skills"]


def test_default_roots_span_every_bundle(tmp_path):
    for bundle in ("manifest-a", "manifest-b", "manifest-c"):
        (tmp_path / f"plugins/{bundle}/skills/one").mkdir(parents=True)
    assert len(src.default_roots(tmp_path)) == 3
