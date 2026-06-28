"""Run reporting — JUnit XML + console summary (T018), redacted (T025).

JUnit is hand-written with stdlib ``ElementTree`` (research R3): one
``<testsuite>`` per app, one ``<testcase>`` per test, ``<failure>`` for fails and
``<skipped>`` for blocked-downstream. Every string emitted to XML or console is
passed through the :class:`Redactor` so a registered secret can never leak
(FR-013, SC-006). Functions accept a single ``RunReport`` or a list (multi-app).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import RunReport
from .redact import Redactor


def _as_list(reports: RunReport | list[RunReport]) -> list[RunReport]:
    return [reports] if isinstance(reports, RunReport) else list(reports)


def _test_detail(result) -> str:
    """All step lines for one test, for the <failure> body / console verbose."""
    return "\n".join(f"  step {s.name}: {s.status}" + (f" — {s.message}" if s.message else "")
                     for s in result.steps)


def _summary_msg(result) -> str:
    """Short message for the first non-passing step (the <failure>/<skipped> attr)."""
    for s in result.steps:
        if s.status != "passed":
            return f"{s.name}: {s.status}" + (f" — {s.message}" if s.message else "")
    return result.status


def write_junit(reports: RunReport | list[RunReport], path: str, redactor: Redactor) -> None:
    root = ET.Element("testsuites")
    for rep in _as_list(reports):
        failures = sum(1 for r in rep.results if r.status == "failed")
        skipped = sum(1 for r in rep.results if r.status == "blocked")
        suite = ET.SubElement(root, "testsuite", {
            "name": rep.app,
            "tests": str(len(rep.results)),
            "failures": str(failures),
            "skipped": str(skipped),
            "time": f"{sum(r.duration_s for r in rep.results):.3f}",
        })
        for r in rep.results:
            case = ET.SubElement(suite, "testcase", {
                "name": r.id,
                "classname": f"{rep.app}.{r.tier}",
                "time": f"{r.duration_s:.3f}",
            })
            if r.status == "failed":
                node = ET.SubElement(case, "failure", {"message": redactor.scrub(_summary_msg(r))})
                node.text = redactor.scrub(_test_detail(r))
            elif r.status == "blocked":
                ET.SubElement(case, "skipped", {"message": redactor.scrub(_summary_msg(r))})
    # Pretty-print via stdlib indent (no XML *parsing* round-trip → no XXE surface).
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
    Path(path).write_text(xml + "\n", encoding="utf-8")


_ICON = {"passed": "PASS", "failed": "FAIL", "blocked": "BLOCK"}


def format_summary(reports: RunReport | list[RunReport], redactor: Redactor) -> str:
    lines: list[str] = []
    for rep in _as_list(reports):
        lines.append(f"== {rep.app} (tier {rep.tier}) ==")
        if not rep.results:
            lines.append("  EMPTY: no tests matched this tier (coverage gap, not a pass)")
        # Failures/blocked first so they are surfaced at the top (US2 scenario 3).
        ordered = sorted(rep.results, key=lambda r: r.status == "passed")
        for r in ordered:
            line = f"  [{_ICON.get(r.status, r.status)}] {r.id} ({r.tier}, {r.duration_s:.2f}s)"
            if r.status != "passed":
                line += f" — {_summary_msg(r)}"
            lines.append(redactor.scrub(line))
        lines.append(f"  verdict: {rep.verdict}  exit: {rep.exit_code}")
    return "\n".join(lines)


def print_summary(reports: RunReport | list[RunReport], redactor: Redactor,
                  stream=sys.stdout) -> None:
    print(format_summary(reports, redactor), file=stream)


def aggregate_exit(reports: RunReport | list[RunReport]) -> int:
    """Worst-case gating exit across apps: any FAIL→1, else any EMPTY→2, else 0."""
    reps = _as_list(reports)
    if any(r.verdict == "FAIL" for r in reps):
        return 1
    if any(r.verdict == "EMPTY" for r in reps):
        return 2
    return 0
