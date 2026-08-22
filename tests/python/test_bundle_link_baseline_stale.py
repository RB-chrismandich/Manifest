"""F2: the ratchet's other half. tools/bundle_link_baseline.py's `new_violations`
suppresses a violation the baseline already records, but never required a
stale allowance -- one whose recorded count exceeds what the current scan
still finds -- to be removed. Fixing a violation without shrinking the
baseline left the allowance available forever, so an identical citation
reintroduced later landed right back at the old count and passed silently.

`stale_entries()` (tools/bundle_link_baseline.py) closes that gap: a baseline
entry whose count exceeds the current scan's count for that key is now a hard
failure, distinct from a new violation, naming the exact `--update-baseline`
command that clears it. See that module's docstring for the full rationale,
including why a citation merely relocated within the same file is a
deliberately accepted non-failure rather than a residual gap.

Split from test_bundle_link_baseline.py purely to stay under the
C-SIZE/CON-002 file-line ceiling; both files share fixtures from
_bundle_link_baseline_harness.py.
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


# --- stale_entries(): the primitive ------------------------------------------


def test_stale_entries_flags_a_baseline_count_that_exceeds_the_current_scan(
    baseline_mod, checker_mod, tmp_path
):
    """A baseline recording 2 occurrences of a citation the current scan only
    finds once is stale by 1 -- the exact value apply()/report() surface."""
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 2}
    )
    remaining = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")

    stale = baseline_mod.stale_entries([remaining], baseline, tmp_path)

    assert stale == [(("s/SKILL.md", "cross-bundle-path", "docs/X.md"), 2, 1)]


def test_stale_entries_flags_a_violation_fixed_down_to_zero_occurrences(
    baseline_mod, checker_mod, tmp_path
):
    """F2's core reproduction: the baseline still allows 1 occurrence but the
    current scan finds none at all -- fixed without shrinking the baseline."""
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 1}
    )

    stale = baseline_mod.stale_entries([], baseline, tmp_path)

    assert stale == [(("s/SKILL.md", "cross-bundle-path", "docs/X.md"), 1, 0)]


def test_stale_entries_is_empty_when_the_scan_matches_or_exceeds_the_baseline(
    baseline_mod, checker_mod, tmp_path
):
    """Staleness is strictly a shrink the baseline missed; a matching or
    rising count is `new_violations`' concern, not `stale_entries`'."""
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 1}
    )
    matching = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")
    extra = _violation(checker_mod, tmp_path, 9, "cross-bundle-path", "docs/X.md")

    assert baseline_mod.stale_entries([matching], baseline, tmp_path) == []
    assert baseline_mod.stale_entries([matching, extra], baseline, tmp_path) == []


def test_stale_entries_is_empty_when_the_same_citation_moves_within_the_same_file(
    baseline_mod, checker_mod, tmp_path
):
    """A citation relocated to a different line in the same file is not a
    shrink -- the count is unchanged, so it is neither stale nor new. This is
    the deliberately-accepted trade-off documented in bundle_link_baseline's
    module docstring: the key omits the line number on purpose, and this
    scenario is the price of that choice. Confirmed correct here, not a
    residual gap left uncovered by accident."""
    baseline = baseline_mod.Baseline(
        counts={("s/SKILL.md", "cross-bundle-path", "docs/X.md"): 1}
    )
    relocated = _violation(checker_mod, tmp_path, 40, "cross-bundle-path", "docs/X.md")

    assert baseline_mod.stale_entries([relocated], baseline, tmp_path) == []
    assert baseline_mod.new_violations([relocated], baseline, tmp_path) == []


# --- apply()/report(): the fix-then-reintroduce round trip -------------------


def test_apply_flags_a_stale_entry_when_a_fix_does_not_update_the_baseline(
    baseline_mod, checker_mod, tmp_path, monkeypatch
):
    """F2, step 1: baseline a violation, then fix it without regenerating the
    baseline. `apply()` must surface it as stale and `report()` must block --
    this is the gap the finding names: the tool's own suppressed-count
    message claimed the ceiling drops, but nothing enforced it."""
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "baseline.json")
    fixed = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")
    baseline_mod.record((fixed,), tmp_path).write()

    result = baseline_mod.apply((), tmp_path, no_baseline=False)

    assert result.reported == ()
    assert result.stale == ((("s/SKILL.md", "cross-bundle-path", "docs/X.md"), 1, 0),)
    exit_code = baseline_mod.report(result, tmp_path, as_json=False, prog="test-prog")
    assert exit_code == 1


def test_apply_is_clean_once_update_baseline_records_the_fix(
    baseline_mod, checker_mod, tmp_path, monkeypatch
):
    """F2, step 2: running --update-baseline (`write_update`) against the
    now-clean scan clears the stale entry; `apply()` reports neither a new
    violation nor a stale one afterward."""
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "baseline.json")
    fixed = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")
    baseline_mod.record((fixed,), tmp_path).write()
    baseline_mod.write_update((), tmp_path, prog="test-prog")

    result = baseline_mod.apply((), tmp_path, no_baseline=False)

    assert result.reported == ()
    assert result.stale == ()
    exit_code = baseline_mod.report(result, tmp_path, as_json=False, prog="test-prog")
    assert exit_code == 0


def test_apply_blocks_the_same_violation_reintroduced_after_the_baseline_shrank(
    baseline_mod, checker_mod, tmp_path, monkeypatch
):
    """F2, step 3: once the fix is properly baselined at 0, a later
    reintroduction of the identical citation is a genuine new violation, not
    a forgiven one -- closing the full fix-then-reintroduce round trip."""
    monkeypatch.setattr(baseline_mod, "DEFAULT_PATH", tmp_path / "baseline.json")
    fixed = _violation(checker_mod, tmp_path, 5, "cross-bundle-path", "docs/X.md")
    baseline_mod.record((fixed,), tmp_path).write()
    baseline_mod.write_update((), tmp_path, prog="test-prog")

    reintroduced = _violation(
        checker_mod, tmp_path, 9, "cross-bundle-path", "docs/X.md"
    )
    result = baseline_mod.apply((reintroduced,), tmp_path, no_baseline=False)

    assert result.reported == (reintroduced,)
    assert result.stale == ()
    exit_code = baseline_mod.report(result, tmp_path, as_json=False, prog="test-prog")
    assert exit_code == 1


def test_report_text_mode_names_the_stale_entry_and_the_fix_command(
    baseline_mod, tmp_path, capsys
):
    """The stale-entry message must name the exact command a contributor
    runs -- discoverability is the point, not just the failing exit code."""
    stale = ((("s/SKILL.md", "cross-bundle-path", "docs/X.md"), 1, 0),)
    result = baseline_mod.ApplyResult(reported=(), suppressed=0, stale=stale)

    exit_code = baseline_mod.report(result, tmp_path, as_json=False, prog="test-prog")

    _out, err = capsys.readouterr()
    assert exit_code == 1
    assert "s/SKILL.md" in err
    assert "cross-bundle-path" in err
    assert "allows 1" in err
    assert "finds 0" in err
    assert "tools/check_bundle_link_references.py --update-baseline" in err


def test_report_json_mode_includes_stale_baseline_entries(
    baseline_mod, tmp_path, capsys
):
    stale = ((("s/SKILL.md", "cross-bundle-path", "docs/X.md"), 1, 0),)
    result = baseline_mod.ApplyResult(reported=(), suppressed=0, stale=stale)

    exit_code = baseline_mod.report(result, tmp_path, as_json=True, prog="test-prog")

    out, err = capsys.readouterr()
    assert exit_code == 1
    assert '"kind": "cross-bundle-path"' in out
    assert '"baseline_count": 1' in out
    assert '"current_count": 0' in out
    assert err == ""


# --- end-to-end through main(): the real CLI, the real repro from the finding


def test_main_end_to_end_fix_then_reintroduce_the_same_violation(
    checker_mod, tmp_path, monkeypatch, capsys
):
    """The full F2 round trip through the actual CLI entry point: baseline a
    violation, fix it without updating the baseline (must now block, naming
    the stale entry), update the baseline (must go clean), then reintroduce
    the identical citation (must block again as a genuinely new violation --
    not silently forgiven the way the original bug allowed)."""
    skill_dir = tmp_path / "plugins/manifest-demo/skills/demo-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    broken = (
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "Also see `${CLAUDE_PLUGIN_ROOT}/reference/missing.md`.\n"
    )
    fixed = "---\nname: demo-skill\ndescription: demo\n---\nNo broken citation here.\n"
    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(checker_mod.bundle_link_baseline, "DEFAULT_PATH", baseline_path)

    skill_md.write_text(broken, encoding="utf-8")
    assert checker_mod.main(["--repo-root", str(tmp_path), "--update-baseline"]) == 0
    capsys.readouterr()

    # Fix it, but do not update the baseline yet -- must now block.
    skill_md.write_text(fixed, encoding="utf-8")
    exit_code = checker_mod.main(["--repo-root", str(tmp_path)])
    out, err = capsys.readouterr()
    assert exit_code == 1
    assert "stale baseline entry" in err
    assert "--update-baseline" in err

    # Record the fix -- must go clean.
    assert checker_mod.main(["--repo-root", str(tmp_path), "--update-baseline"]) == 0
    capsys.readouterr()
    assert checker_mod.main(["--repo-root", str(tmp_path)]) == 0
    capsys.readouterr()

    # Reintroduce the identical citation later -- must block again, not pass
    # silently the way the original F2 bug allowed.
    skill_md.write_text(broken, encoding="utf-8")
    exit_code = checker_mod.main(["--repo-root", str(tmp_path)])
    out, _err = capsys.readouterr()
    assert exit_code == 1
    assert "missing-bundle-local-target" in out
