"""The ratchet for check_bundle_link_references.py: known violations are
recorded as data, new ones block.

Phase 0 of docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md
deliberately defers fixing the checker's 77 pre-existing findings -- fixing
them means either vendoring shared references into every bundle that cites
them or rewriting the citations, both Phase 1 work. Wiring the checker into
CI unconditionally would make every commit red until Phase 1 lands, which is
how a gate gets bypassed rather than respected. So, as with
``constitution_check.py``/``constitution_baseline.json``, the gate compares
against a recorded baseline: a NEW violation blocks, a pre-existing one does
not, and fixing one lowers the ceiling without anyone editing the baseline.

Keyed on the violation's own identity -- ``(path, kind, value)``, deliberately
NOT the line number, and deliberately NOT a bare per-(path, kind) count. Line
number is excluded so an unrelated edit earlier in the same file (which
shifts every later line) doesn't turn a still-present, still-known citation
into a "new" one. A bare count is exactly what this baseline is NOT: the
constitution checker's ``(file, check)`` -> integer scheme means fixing one
violation and introducing a different one of the same check in the same file
nets to an unchanged count -- the swap is invisible. Here the count is kept
per FULL ``(path, kind, value)`` triple (occasionally >1 -- the same missing
reference is legitimately cited twice in one file in the real baseline), so a
citation with a *different* value never hides behind one that was fixed.

Excluding the line number is a deliberate trade-off with one accepted gap:
moving the same ``(path, kind, value)`` citation to a different line within
the same file -- fixing it at its old location while an equal-or-greater
number of occurrences appear elsewhere in that file -- nets to an unchanged
count and passes cleanly. That is intentional, not an oversight: it is the
identical mechanism that lets an unrelated earlier edit shift line numbers
without manufacturing a false "new" violation, and there is no way to keep
one without the other. A key that included the line would flag the earlier,
harmless case as ratchet-broken far more often than it would ever catch the
narrow, contrived case of a citation relocated to the exact same file. See
``tests/python/test_bundle_link_baseline.py`` for the case this documents.

The other half of the ratchet is enforced by ``stale_entries()``: a baseline
entry whose recorded count *exceeds* what the current scan finds for that key
means a violation was fixed (in whole or in part) without the committed
baseline being brought down to match -- the gap that let a fixed violation
return silently, since a later re-introduction of that identical citation
would otherwise land exactly back at the old, still-allowed count and pass.
``apply()``/``report()`` treat a stale entry as a hard failure, distinct from
a new violation, and name the exact command (``--update-baseline``) that
clears it.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from check_bundle_link_references import Violation

DEFAULT_PATH = Path(__file__).resolve().parent / "bundle_link_baseline.json"
SCHEMA_VERSION = 1

_Key = tuple[str, str, str]  # (repo-relative path, kind, value)


@dataclass(frozen=True, slots=True)
class Baseline:
    """Recorded violation occurrences, keyed by ``(path, kind, value)``."""

    counts: Counter[_Key]

    @classmethod
    def load(cls, path: Path | None = None) -> Baseline:
        # ``path`` resolves against the CURRENT module-level DEFAULT_PATH at
        # call time, not a value frozen into the signature at import time --
        # deliberate, so a caller (a test, most often) can monkeypatch
        # DEFAULT_PATH and every default-path caller picks it up.
        path = DEFAULT_PATH if path is None else path
        if not path.is_file():
            return cls(counts=Counter())
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != SCHEMA_VERSION:
            raise ValueError(
                f"{path}: unsupported baseline version {raw.get('version')!r}"
            )
        counts: Counter[_Key] = Counter()
        for entry in raw.get("violations", []):
            counts[(entry["path"], entry["kind"], entry["value"])] += 1
        return cls(counts=counts)

    def write(self, path: Path | None = None) -> None:
        path = DEFAULT_PATH if path is None else path
        entries = [
            {"path": p, "kind": kind, "value": value}
            for (p, kind, value), n in sorted(self.counts.items())
            for _ in range(n)
        ]
        payload = {
            "version": SCHEMA_VERSION,
            "_comment": (
                "Recorded bundle-local-reference violations as of Phase 0 "
                "(docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md). "
                "The gate blocks on any violation NOT in this list -- fixing one "
                "lowers the ceiling automatically; it is never edited to hide a fix. "
                "Regenerate with: uv run python tools/check_bundle_link_references.py "
                "--update-baseline. An entry may be added by hand only with the "
                "reason in the commit message."
            ),
            "violations": entries,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _key(violation: Violation, root: Path) -> _Key:
    try:
        rel = violation.path.resolve().relative_to(root).as_posix()
    except ValueError:
        rel = violation.path.as_posix()
    return (rel, violation.kind, violation.value)


def new_violations(
    violations: Iterable[Violation], baseline: Baseline, root: Path
) -> list[Violation]:
    """Return only the violations the baseline does not already record.

    Each ``(path, kind, value)`` key may recur (a citation repeated at
    several lines in one file); the first N occurrences up to the baseline's
    recorded count for that key are treated as known, and only occurrences
    past that are new. Order is by line so the reported findings are the
    stable, later-appearing ones rather than an arbitrary subset.
    """
    consumed: Counter[_Key] = Counter()
    excess: list[Violation] = []
    for violation in sorted(violations, key=lambda v: (str(v.path), v.line)):
        key = _key(violation, root)
        consumed[key] += 1
        if consumed[key] > baseline.counts.get(key, 0):
            excess.append(violation)
    return excess


def record(violations: Iterable[Violation], root: Path) -> Baseline:
    """Build a baseline that records exactly the given violations."""
    counts: Counter[_Key] = Counter(_key(v, root) for v in violations)
    return Baseline(counts=counts)


def stale_entries(
    violations: Iterable[Violation], baseline: Baseline, root: Path
) -> list[tuple[_Key, int, int]]:
    """Return baseline entries the current scan no longer justifies.

    A key is stale when its committed count exceeds how many times the
    current scan actually finds that exact ``(path, kind, value)`` -- the
    violation was fixed, in whole or in part, but the baseline was never
    brought down to match. Left unchecked, that stale allowance is exactly
    what lets an identical violation return later and pass silently: its
    count would land back at or below the still-inflated baseline. Each
    result is ``(key, baseline_count, current_count)`` with
    ``baseline_count > current_count``, sorted for stable output.
    """
    current: Counter[_Key] = Counter(_key(v, root) for v in violations)
    return sorted(
        (key, count, current.get(key, 0))
        for key, count in baseline.counts.items()
        if count > current.get(key, 0)
    )


# --- CLI-facing helpers (kept here, not in check_bundle_link_references.py,
# purely because that file is at its own C-SIZE ceiling; these are otherwise
# ordinary CLI plumbing, not part of "the ratchet" conceptually). ----------


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """What ``apply()`` decided for one scan: the record ``report()`` prints.

    Grouped into one value (rather than threaded as separate parameters)
    because the three always travel together from ``apply()`` to ``report()``
    and a fourth field -- staleness -- is exactly what widened ``report()``
    past its parameter ceiling before this existed.
    """

    reported: tuple[Violation, ...]
    suppressed: int
    stale: tuple[tuple[_Key, int, int], ...]


def apply(
    violations: tuple[Violation, ...], root: Path, *, no_baseline: bool
) -> ApplyResult:
    """Split ``violations`` into what to report, how many the baseline held,
    and which baseline entries are now stale (see ``stale_entries()``).

    ``no_baseline`` reproduces pre-ratchet behaviour: every violation is
    reported, nothing is suppressed, and staleness is not evaluated -- for a
    human running the full audit with the baseline set aside entirely.
    """
    if no_baseline:
        return ApplyResult(violations, 0, ())
    baseline = Baseline.load()
    reported = tuple(new_violations(violations, baseline, root))
    stale = tuple(stale_entries(violations, baseline, root))
    return ApplyResult(reported, len(violations) - len(reported), stale)


def write_update(violations: tuple[Violation, ...], root: Path, *, prog: str) -> int:
    """Regenerate the baseline from ``violations``, report it, and exit 0."""
    record(violations, root).write()
    print(
        f"{prog}: baseline written to {DEFAULT_PATH} ({len(violations)} violation(s))"
    )
    return 0


def report(result: ApplyResult, root: Path, as_json: bool, *, prog: str) -> int:
    """Print ``result`` (JSON or text) and return the process exit code --
    1 if there is a reported violation or a stale baseline entry, else 0."""
    if as_json:
        print(
            json.dumps(
                {
                    "violations": [v.as_json(root) for v in result.reported],
                    "stale_baseline_entries": [
                        {
                            "path": p,
                            "kind": kind,
                            "value": value,
                            "baseline_count": baseline_count,
                            "current_count": current_count,
                        }
                        for (p, kind, value), baseline_count, current_count in (
                            result.stale
                        )
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for v in result.reported:
            try:
                display = v.path.relative_to(root)
            except ValueError:
                display = v.path
            print(f"{display}:{v.line}: {v.kind}: {v.message}")
        if result.suppressed:
            print(
                f"{prog}: {result.suppressed} pre-existing violation(s) held at "
                f"the baseline ({DEFAULT_PATH.name}); fixing one lowers it "
                "permanently.",
                file=sys.stderr,
            )
        for (p, kind, value), baseline_count, current_count in result.stale:
            print(
                f"{prog}: stale baseline entry {p}:{kind}:{value!r} allows "
                f"{baseline_count}, but the current scan only finds "
                f"{current_count} -- this violation was fixed without "
                "shrinking the baseline. Run `uv run python "
                "tools/check_bundle_link_references.py --update-baseline` "
                "to record the fix.",
                file=sys.stderr,
            )
    return 1 if (result.reported or result.stale) else 0
