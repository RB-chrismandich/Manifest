"""The ratchet: pre-existing debt is held, new debt is reported.

The baseline is the one component whose failure mode is silent. A checker that
crashes gets fixed; a baseline that quietly allows everything reports a clean
run forever and nobody looks again. So the cases pinned here are mostly the
"must NOT pass" ones: an unreadable version, an advisory check sneaking into the
recorded counts, one added violation hiding behind an existing allowance.

Nothing here touches the repo's committed baseline — every path is under
tmp_path, and `record()` is only ever asked to write there.
"""

import json
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from constitution import baseline as baseline_mod
from constitution import registry, source
from constitution.checks import run_checks
from constitution.findings import Finding

REG = registry.load()

# One blocking check and one advisory one, taken from the registry rather than
# named literally, so a posture flip in the YAML surfaces here as a failure of
# the assumption instead of a test that quietly stops testing anything.
BLOCKING = next(c for c in REG.checks.values() if not c.advisory)
ADVISORY = next(c for c in REG.checks.values() if c.advisory)


def finding(path: Path, line: int, check=None) -> Finding:
    check = check or BLOCKING
    return Finding(
        check=check.id,
        article=check.article,
        severity="error",
        path=path,
        line=line,
        message=f"synthetic {check.id} violation",
        remedy="fix it",
    )


def baseline_file(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "constitution_baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def loaded_baseline(tmp_path: Path, files: dict) -> "baseline_mod.Baseline":
    """A baseline read back from a real file — never the repo's committed one."""
    payload = {"version": baseline_mod.SCHEMA_VERSION, "files": files}
    return baseline_mod.Baseline.load(baseline_file(tmp_path, payload), tmp_path)


def source_path(tmp_path: Path, name: str = "mod.py") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1 — no baseline means no suppression
# ---------------------------------------------------------------------------


def test_absent_baseline_reports_every_finding(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)
    findings = [finding(path, 10), finding(path, 20), finding(path, 30)]

    empty = baseline_mod.Baseline.load(root / "nope.json", root)

    assert empty.counts == {}
    assert baseline_mod.over_baseline(findings, empty, REG) == findings


def test_empty_baseline_file_reports_every_finding(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)
    findings = [finding(path, 10), finding(path, 20)]

    loaded = loaded_baseline(root, {})

    assert baseline_mod.over_baseline(findings, loaded, REG) == findings


# ---------------------------------------------------------------------------
# 2 — an exact entry suppresses exactly those findings
# ---------------------------------------------------------------------------


def test_exact_entry_suppresses_all_of_them(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)
    findings = [finding(path, 10), finding(path, 20), finding(path, 30)]
    loaded = loaded_baseline(root, {"mod.py": {BLOCKING.id: 3}})

    assert baseline_mod.over_baseline(findings, loaded, REG) == []


def test_entry_is_scoped_to_its_file_and_check(tmp_path):
    """An allowance for one file/check may not excuse another's."""
    root = tmp_path.resolve()
    mine, other = source_path(root, "mod.py"), source_path(root, "other.py")
    loaded = loaded_baseline(root, {"mod.py": {BLOCKING.id: 2}})

    reported = baseline_mod.over_baseline(
        [
            finding(mine, 10),
            finding(mine, 20),
            finding(other, 5),
            finding(mine, 30, ADVISORY),
        ],
        loaded,
        REG,
    )

    assert {(f.path.name, f.check) for f in reported} == {
        ("other.py", BLOCKING.id),
        ("mod.py", ADVISORY.id),
    }


# ---------------------------------------------------------------------------
# 3 — one added violation is reported, and only one
# ---------------------------------------------------------------------------


def test_one_new_violation_above_the_entry_is_reported(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)
    loaded = loaded_baseline(root, {"mod.py": {BLOCKING.id: 2}})

    reported = baseline_mod.over_baseline(
        [finding(path, 10), finding(path, 20), finding(path, 30)], loaded, REG
    )

    assert len(reported) == 1
    assert reported[0].line == 30, (
        "the surfaced finding should be stable, not arbitrary"
    )


def test_new_violation_of_an_unbaselined_check_is_reported(tmp_path):
    """A file with an entry for one check has no allowance for a different one."""
    root = tmp_path.resolve()
    path = source_path(root)
    loaded = loaded_baseline(root, {"mod.py": {BLOCKING.id: 2}})

    reported = baseline_mod.over_baseline(
        [finding(path, 10), finding(path, 20), finding(path, 40, ADVISORY)], loaded, REG
    )

    assert [(f.check, f.line) for f in reported] == [(ADVISORY.id, 40)]


# ---------------------------------------------------------------------------
# 4 — fixing violations is the intended direction, never an error
# ---------------------------------------------------------------------------


def test_fewer_violations_than_recorded_is_clean_not_an_error(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)
    loaded = loaded_baseline(root, {"mod.py": {BLOCKING.id: 5}})

    assert baseline_mod.over_baseline([finding(path, 10)], loaded, REG) == []
    assert baseline_mod.over_baseline([], loaded, REG) == []
    # The stale entry over-allows until regenerated: re-adding up to the old
    # count stays silent. That is the documented trade (counts, not lines) and
    # the reason --update-baseline exists.
    assert (
        baseline_mod.over_baseline([finding(path, i) for i in range(5)], loaded, REG)
        == []
    )
    assert (
        len(
            baseline_mod.over_baseline(
                [finding(path, i) for i in range(6)], loaded, REG
            )
        )
        == 1
    )


# ---------------------------------------------------------------------------
# 5 — an unknown schema version raises; it must never mean "allow everything"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version", [baseline_mod.SCHEMA_VERSION + 1, 0, "1", None, "1.0.0"], ids=repr
)
def test_unknown_baseline_version_raises(tmp_path, version):
    root = tmp_path.resolve()
    path = baseline_file(
        root, {"version": version, "files": {"mod.py": {BLOCKING.id: 99}}}
    )

    with pytest.raises(ValueError) as excinfo:
        baseline_mod.Baseline.load(path, root)

    assert str(path) in str(excinfo.value), "the error must name the file to fix"


def test_missing_version_key_raises(tmp_path):
    root = tmp_path.resolve()
    path = baseline_file(root, {"files": {"mod.py": {BLOCKING.id: 99}}})

    with pytest.raises(ValueError):
        baseline_mod.Baseline.load(path, root)


def test_malformed_baseline_raises_rather_than_loading_empty(tmp_path):
    root = tmp_path.resolve()
    path = root / "constitution_baseline.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        baseline_mod.Baseline.load(path, root)


# ---------------------------------------------------------------------------
# 6 — record() keeps advisory checks out of the ratchet
# ---------------------------------------------------------------------------


def test_record_omits_advisory_checks(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)

    recorded = baseline_mod.record(
        [
            finding(path, 10),
            finding(path, 20, ADVISORY),
            finding(path, 30, ADVISORY),
        ],
        root,
        REG,
    )

    assert recorded.counts == {"mod.py": {BLOCKING.id: 1}}
    assert ADVISORY.id not in recorded.counts["mod.py"]


def test_record_omits_findings_from_unknown_checks(tmp_path):
    """An id the registry does not know cannot be granted an allowance."""
    root = tmp_path.resolve()
    path = source_path(root)
    ghost = Finding(
        check="C-GHOST",
        article="CON-001",
        severity="error",
        path=path,
        line=7,
        message="from a check that no longer exists",
        remedy="fix it",
    )

    assert baseline_mod.record([ghost], root, REG).counts == {}


def test_advisory_findings_are_never_suppressed_by_a_recorded_baseline(tmp_path):
    """The two halves compose: what record() omits, over_baseline() still reports."""
    root = tmp_path.resolve()
    path = source_path(root)
    findings = [finding(path, 10), finding(path, 20, ADVISORY)]

    recorded = baseline_mod.record(findings, root, REG)

    assert baseline_mod.over_baseline(findings, recorded, REG) == [findings[1]]


# ---------------------------------------------------------------------------
# 7 — round trip
# ---------------------------------------------------------------------------


def test_record_write_load_round_trip(tmp_path):
    root = tmp_path.resolve()
    first, second = source_path(root, "mod.py"), source_path(root, "pkg/other.py")
    findings = [
        finding(first, 10),
        finding(first, 20),
        finding(second, 5),
        finding(second, 15, ADVISORY),
    ]

    recorded = baseline_mod.record(findings, root, REG)
    target = root / "out.json"
    recorded.write(target)
    reloaded = baseline_mod.Baseline.load(target, root)

    assert reloaded.counts == recorded.counts
    assert reloaded.counts == {
        "mod.py": {BLOCKING.id: 2},
        "pkg/other.py": {BLOCKING.id: 1},
    }
    assert baseline_mod.over_baseline(findings, reloaded, REG) == [findings[3]]


def test_written_baseline_declares_its_schema_version(tmp_path):
    root = tmp_path.resolve()
    target = root / "out.json"
    baseline_mod.Baseline(counts={"mod.py": {BLOCKING.id: 1}}, root=root).write(target)

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["version"] == baseline_mod.SCHEMA_VERSION
    assert payload["files"] == {"mod.py": {BLOCKING.id: 1}}


def test_allowance_reads_back_what_was_recorded(tmp_path):
    root = tmp_path.resolve()
    path = source_path(root)
    recorded = baseline_mod.record([finding(path, 1), finding(path, 2)], root, REG)

    assert recorded.allowance(path, BLOCKING.id) == 2
    assert recorded.allowance(path, ADVISORY.id) == 0
    assert recorded.allowance(root / "unseen.py", BLOCKING.id) == 0


# ---------------------------------------------------------------------------
# End-to-end against real check output, not hand-built findings
# ---------------------------------------------------------------------------


def module_with_wide_functions(tmp_path: Path, count: int) -> Path:
    """A file whose functions each exceed the python `parameters` ceiling."""
    over = REG.languages["python"].threshold("parameters") + 1
    params = ", ".join(f"p{i}" for i in range(over))
    body = "\n\n".join(f"def f{n}({params}):\n    return {n}" for n in range(count))
    path = tmp_path / "wide.py"
    path.write_text(textwrap.dedent(body) + "\n", encoding="utf-8")
    return path


def size_findings(path: Path):
    return run_checks(source.SourceFile.load(path, REG), REG, only=["C-SIZE"])


def test_real_findings_are_ratcheted_not_reported_twice(tmp_path):
    root = tmp_path.resolve()
    before = size_findings(module_with_wide_functions(root, 2))
    assert len(before) == 2, f"fixture did not produce two C-SIZE findings: {before}"

    recorded = baseline_mod.record(before, root, REG)
    target = root / "baseline.json"
    recorded.write(target)
    loaded = baseline_mod.Baseline.load(target, root)

    assert baseline_mod.over_baseline(before, loaded, REG) == []

    after = size_findings(module_with_wide_functions(root, 3))
    reported = baseline_mod.over_baseline(after, loaded, REG)

    assert len(reported) == 1, f"expected exactly the added violation, got {reported}"
    assert reported[0].check == "C-SIZE"
