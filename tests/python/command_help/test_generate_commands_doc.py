"""T007 — failing-first tests for generate_commands_doc.py (spec 362, US1).

Render correctness + the --check drift contract (in-sync=0, drift=1).
Written before the implementation — must FAIL first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "configs/claude/scripts"))
import generate_commands_doc as gen

CATALOG = {
    "generated_for_platform": "claude",
    "categories": [
        {"key": "git-pr", "label": "Git & PRs", "order": 1},
        {"key": "docs", "label": "Documentation", "order": 2},
    ],
    "commands": [
        {
            "name": "branch-clean",
            "description": "Prune stale branches.",
            "when_to_use": "Use when pruning merged or gone branches",
            "category": "git-pr",
            "availability": {
                "service_enabled": True,
                "deployed_to_platform": True,
                "status": "available",
                "reason": None,
            },
        },
        {
            "name": "docs-all",
            "description": "Refresh all docs.",
            "when_to_use": "Refresh all docs.",
            "category": "docs",
            "availability": {
                "service_enabled": True,
                "deployed_to_platform": True,
                "status": "available",
                "reason": None,
            },
        },
        {
            "name": "skillclaw-thing",
            "description": "A gated tool.",
            "when_to_use": "Gated.",
            "category": "git-pr",
            "availability": {
                "service_enabled": False,
                "deployed_to_platform": True,
                "status": "unavailable",
                "reason": "service disabled",
            },
        },
    ],
}


# --- render correctness ----------------------------------------------------- #
def test_render_section_groups_by_category_label():
    section = gen.render_section(CATALOG)
    assert "Git & PRs" in section
    assert "Documentation" in section
    assert "`/branch-clean`" in section
    assert "`/docs-all`" in section


def test_render_section_marks_unavailable():
    section = gen.render_section(CATALOG)
    assert "skillclaw-thing" in section
    assert "service disabled" in section


def test_render_section_is_deterministic():
    assert gen.render_section(CATALOG) == gen.render_section(CATALOG)


def test_render_section_has_markers():
    section = gen.render_section(CATALOG)
    assert gen.BEGIN_MARKER in section
    assert gen.END_MARKER in section


def test_compact_index_has_no_descriptions():
    idx = gen.render_compact_index(CATALOG)
    assert "`/branch-clean`" in idx
    # compact index links names but omits the prose description
    assert "Prune stale branches." not in idx


# --- inject / extract round-trip -------------------------------------------- #
def test_inject_replaces_between_markers():
    doc = f"# Guide\n\nIntro.\n\n{gen.BEGIN_MARKER}\nOLD\n{gen.END_MARKER}\n\nFooter.\n"
    out = gen.inject(doc, gen.render_section(CATALOG))
    assert "Intro." in out and "Footer." in out
    assert "OLD" not in out
    assert "`/branch-clean`" in out


def test_inject_appends_when_markers_absent():
    doc = "# Guide\n\nNo markers here.\n"
    out = gen.inject(doc, gen.render_section(CATALOG))
    assert "No markers here." in out
    assert gen.BEGIN_MARKER in out and "`/branch-clean`" in out


# --- --check drift contract ------------------------------------------------- #
def test_check_in_sync_returns_zero(tmp_path):
    doc = tmp_path / "COMMANDS.md"
    gen.write_doc(str(doc), CATALOG, base_text="# Guide\n\nIntro.\n")
    assert gen.check_doc(str(doc), CATALOG) == 0


def test_check_drift_returns_one(tmp_path):
    doc = tmp_path / "COMMANDS.md"
    gen.write_doc(str(doc), CATALOG, base_text="# Guide\n\nIntro.\n")
    # mutate the committed doc → drift
    doc.write_text(doc.read_text().replace("branch-clean", "branch-cleaned"))
    assert gen.check_doc(str(doc), CATALOG) == 1


def test_check_missing_doc_returns_two(tmp_path):
    assert gen.check_doc(str(tmp_path / "absent.md"), CATALOG) == 2


def test_write_is_idempotent(tmp_path):
    doc = tmp_path / "COMMANDS.md"
    gen.write_doc(str(doc), CATALOG, base_text="# Guide\n\nIntro.\n")
    first = doc.read_text()
    gen.write_doc(str(doc), CATALOG)  # re-run, no base change
    assert doc.read_text() == first
