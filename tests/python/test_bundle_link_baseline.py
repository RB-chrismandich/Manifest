"""The Phase 0 ratchet for check_bundle_link_references.py: a baseline of
already-known violations must suppress exactly those, never a genuinely new
one -- even when the new one shares a file and kind with a known one (the
failure mode a bare per-(file, check) count would miss). See
tools/bundle_link_baseline.py's module docstring.

The other half of the ratchet -- a fixed violation whose baseline entry was
never shrunk (F2) -- is covered in test_bundle_link_baseline_stale.py, split
out purely to stay under the C-SIZE/CON-002 file-line ceiling; see
_bundle_link_baseline_harness.py for the shared fixtures both files use.
"""

from __future__ import annotations

import pytest
from _bundle_link_baseline_harness import baseline_module, checker_module
from _bundle_link_baseline_harness import violation as _violation


@pytest.fixture()
def baseline_mod():
    return baseline_module()


@pytest.fixture()
def checker_mod():
    return checker_module()


# --- Baseline.load / .write round trip -------------------------------------


def test_write_then_load_round_trips_counts_including_duplicates(
    baseline_mod, tmp_path
):
    path = tmp_path / "baseline.json"
    baseline = baseline_mod.Baseline(
        counts={
            ("a/SKILL.md", "cross-bundle-path", "docs/X.md"): 2,
            ("b/SKILL.md", "missing-bundled-reference", "y.md"): 1,
        }
    )

    baseline.write(path)
    reloaded = baseline_mod.Baseline.load(path)

    assert reloaded.counts == baseline.counts


def test_load_missing_file_returns_empty_baseline(baseline_mod, tmp_path):
    baseline = baseline_mod.Baseline.load(tmp_path / "does-not-exist.json")
    assert baseline.counts == {}


def test_load_rejects_unsupported_schema_version(baseline_mod, tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text('{"version": 99, "violations": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported baseline version"):
        baseline_mod.Baseline.load(path)


def test_load_and_write_default_to_the_module_default_path_dynamically(
    baseline_mod, tmp_path, monkeypatch
):
    """A caller that monkeypatches DEFAULT_PATH after import (as a test does)
    must have every no-argument call pick it up -- proves the default is
    resolved at call time, not frozen into the signature at import time."""
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "patched.json")
    baseline = baseline_mod.Baseline(counts={("f.md", "cross-bundle-path", "x.md"): 1})

    baseline.write()

    assert (tmp_path / "patched.json").is_file()
    assert baseline_mod.Baseline.load().counts == baseline.counts


# --- new_violations: the actual ratchet logic -------------------------------


def test_new_violations_suppresses_a_known_citation_regardless_of_line(
    baseline_mod, checker_mod, tmp_path
):
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 1}
    )
    # Line 40, not the line the baseline was recorded against -- an unrelated
    # edit earlier in the file shifted it. Must still be suppressed.
    violation = _violation(checker_mod, tmp_path, 40, "cross-bundle-path", "docs/X.md")

    excess = baseline_mod.new_violations([violation], baseline, tmp_path)

    assert excess == []


def test_new_violations_reports_a_citation_the_baseline_never_recorded(
    baseline_mod, checker_mod, tmp_path
):
    baseline = baseline_mod.Baseline(counts={})
    violation = _violation(checker_mod, tmp_path, 10, "cross-bundle-path", "docs/X.md")

    excess = baseline_mod.new_violations([violation], baseline, tmp_path)

    assert excess == [violation]


def test_new_violations_does_not_let_a_different_citation_hide_behind_a_fixed_one(
    baseline_mod, checker_mod, tmp_path
):
    """The exact failure mode a bare (file, check) count misses: the baseline
    holds one `cross-bundle-path` violation for this file/citation. Fixing it
    and introducing a DIFFERENT cross-bundle-path citation in the same file
    must not net to "still within budget" -- the new citation's `value`
    differs, so its (path, kind, value) key was never recorded."""
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/OLD.md"): 1}
    )
    replacement = _violation(
        checker_mod, tmp_path, 10, "cross-bundle-path", "docs/NEW.md"
    )

    excess = baseline_mod.new_violations([replacement], baseline, tmp_path)

    assert excess == [replacement]


def test_new_violations_reports_only_occurrences_past_the_recorded_count(
    baseline_mod, checker_mod, tmp_path
):
    """Same (path, kind, value) cited twice is baselined at count 2; a third,
    genuinely new occurrence of that identical citation must still surface."""
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 2}
    )
    known_a = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")
    known_b = _violation(checker_mod, tmp_path, 12, "cross-bundle-path", "docs/X.md")
    third = _violation(checker_mod, tmp_path, 20, "cross-bundle-path", "docs/X.md")

    excess = baseline_mod.new_violations([known_a, known_b, third], baseline, tmp_path)

    assert excess == [third]


# --- record(): building a baseline from live findings -----------------------


def test_record_captures_exact_multiplicity(baseline_mod, checker_mod, tmp_path):
    violations = [
        _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md"),
        _violation(checker_mod, tmp_path, 12, "cross-bundle-path", "docs/X.md"),
        _violation(checker_mod, tmp_path, 20, "missing-bundled-reference", "y.md"),
    ]

    baseline = baseline_mod.record(violations, tmp_path)

    assert baseline.counts == {
        ("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 2,
        ("s/SKILL.md", "missing-bundled-reference", "y.md"): 1,
    }


def test_record_then_new_violations_is_clean_against_its_own_source(
    baseline_mod, checker_mod, tmp_path
):
    """A baseline recorded from a given set of violations must report zero
    excess against that exact same set -- the "adopt today's debt" case."""
    violations = [
        _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md"),
        _violation(checker_mod, tmp_path, 12, "cross-bundle-path", "docs/X.md"),
    ]
    baseline = baseline_mod.record(violations, tmp_path)

    assert baseline_mod.new_violations(violations, baseline, tmp_path) == []


# --- apply / write_update / report: the CLI-facing helpers ------------------


def test_apply_with_no_baseline_reports_everything_unsuppressed(
    baseline_mod, checker_mod, tmp_path, monkeypatch
):
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "unused.json")
    violation = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")

    result = baseline_mod.apply((violation,), tmp_path, no_baseline=True)

    assert result.reported == (violation,)
    assert result.suppressed == 0
    assert result.stale == ()


def test_apply_suppresses_what_the_baseline_at_default_path_records(
    baseline_mod, checker_mod, tmp_path, monkeypatch
):
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "baseline.json")
    known = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")
    new = _violation(checker_mod, tmp_path, 9, "missing-bundled-reference", "y.md")
    baseline_mod.record((known,), tmp_path).write()

    result = baseline_mod.apply((known, new), tmp_path, no_baseline=False)

    assert result.reported == (new,)
    assert result.suppressed == 1
    assert result.stale == ()


def test_write_update_writes_a_baseline_that_makes_the_source_set_clean(
    baseline_mod, checker_mod, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "baseline.json")
    violation = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")

    exit_code = baseline_mod.write_update((violation,), tmp_path, prog="test-prog")

    assert exit_code == 0
    assert "test-prog: baseline written to" in capsys.readouterr().out
    result = baseline_mod.apply((violation,), tmp_path, no_baseline=False)
    assert result.reported == ()
    assert result.suppressed == 1
    assert result.stale == ()


def test_report_text_mode_names_only_new_violations_and_notes_suppressed_count(
    baseline_mod, checker_mod, tmp_path, capsys
):
    new = _violation(checker_mod, tmp_path, 9, "missing-bundled-reference", "y.md")
    result = baseline_mod.ApplyResult(reported=(new,), suppressed=5, stale=())

    exit_code = baseline_mod.report(result, tmp_path, as_json=False, prog="test-prog")

    out, err = capsys.readouterr()
    assert "s/SKILL.md:9: missing-bundled-reference" in out
    assert "5 pre-existing violation(s) held at the baseline" in err
    assert exit_code == 1


def test_report_returns_zero_and_stays_silent_when_nothing_new(
    baseline_mod, tmp_path, capsys
):
    result = baseline_mod.ApplyResult(reported=(), suppressed=77, stale=())

    exit_code = baseline_mod.report(result, tmp_path, as_json=False, prog="test-prog")

    out, err = capsys.readouterr()
    assert out == ""
    assert "77 pre-existing violation(s)" in err
    assert exit_code == 0


def test_report_json_mode_omits_the_suppressed_footer(baseline_mod, tmp_path, capsys):
    result = baseline_mod.ApplyResult(reported=(), suppressed=3, stale=())

    exit_code = baseline_mod.report(result, tmp_path, as_json=True, prog="test-prog")

    out, err = capsys.readouterr()
    assert '"violations": []' in out
    assert err == ""
    assert exit_code == 0


# --- end-to-end through main(): the actual CI entry point -------------------


def test_main_default_run_exits_zero_when_only_baselined_violations_exist(
    checker_mod, tmp_path, monkeypatch, capsys
):
    skill_dir = tmp_path / "plugins/manifest-demo/skills/demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "Follow the bundled `sub-agent-dispatch.md` selection rules.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        checker_mod.bundle_link_baseline, "DEFAULT_PATH", tmp_path / "baseline.json"
    )
    exit_code = checker_mod.main(["--repo-root", str(tmp_path), "--update-baseline"])
    assert exit_code == 0
    capsys.readouterr()

    exit_code = checker_mod.main(["--repo-root", str(tmp_path)])

    out, _err = capsys.readouterr()
    assert out.strip() == ""
    assert exit_code == 0


def test_main_default_run_exits_one_and_names_only_the_new_violation(
    checker_mod, tmp_path, monkeypatch, capsys
):
    skill_dir = tmp_path / "plugins/manifest-demo/skills/demo-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "Follow the bundled `sub-agent-dispatch.md` selection rules.\n",
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(checker_mod.bundle_link_baseline, "DEFAULT_PATH", baseline_path)
    assert checker_mod.main(["--repo-root", str(tmp_path), "--update-baseline"]) == 0
    capsys.readouterr()

    # A second, brand-new violation kind appears alongside the baselined one.
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8")
        + "Also see `${CLAUDE_PLUGIN_ROOT}/reference/missing.md`.\n",
        encoding="utf-8",
    )

    exit_code = checker_mod.main(["--repo-root", str(tmp_path)])

    out, _err = capsys.readouterr()
    assert exit_code == 1
    assert "missing-bundle-local-target" in out
    assert "sub-agent-dispatch.md" not in out  # the baselined one stays silent
