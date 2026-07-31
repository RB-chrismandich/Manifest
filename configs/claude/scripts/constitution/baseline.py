"""The ratchet: existing debt is recorded, new debt blocks.

A constitution introduced against an existing codebase has one failure mode
that kills it — the first person to touch a legacy file gets blocked on
violations they did not write, learns the gate is noise, and starts bypassing
it. So the gate compares against a recorded baseline: you may not add a
violation to a file, and every violation you remove lowers the ceiling
permanently.

Counts rather than line numbers on purpose: line numbers churn on every edit,
which would make the baseline a merge-conflict generator and, worse, would let
a stale entry silently excuse a genuinely new violation.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .findings import Finding
from .registry import Registry

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "constitution_baseline.json"
)
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Baseline:
    """Recorded violation counts, keyed by repo-relative path then check id."""

    counts: dict[str, dict[str, int]]
    root: Path

    @classmethod
    def load(cls, path: Path, root: Path) -> Baseline:
        if not path.is_file():
            return cls(counts={}, root=root)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != SCHEMA_VERSION:
            raise ValueError(
                f"{path}: unsupported baseline version {raw.get('version')!r}"
            )
        return cls(counts=dict(raw.get("files") or {}), root=root)

    def allowance(self, path: Path, check: str) -> int:
        return self.counts.get(self.key(path), {}).get(check, 0)

    def key(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def write(self, path: Path) -> None:
        payload = {
            "version": SCHEMA_VERSION,
            "_comment": (
                "Recorded violation counts at the time the Code Constitution was adopted. "
                "The gate blocks when a file's count for a check RISES above its entry. "
                "Lower these by fixing; regenerate with constitution_check.py --update-baseline. "
                "An entry may never be raised without the reason in the commit message."
            ),
            "files": {
                p: dict(sorted(c.items())) for p, c in sorted(self.counts.items())
            },
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )


def over_baseline(
    findings: list[Finding], baseline: Baseline, registry: Registry
) -> list[Finding]:
    """Return only the findings that exceed what the baseline already allows.

    Within a (file, check) group the newest-looking findings are surfaced last,
    so the ones reported are stable across unrelated edits to the same file.
    """
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault((baseline.key(finding.path), finding.check), []).append(
            finding
        )

    excess: list[Finding] = []
    for (key, check), group in grouped.items():
        allowed = baseline.counts.get(key, {}).get(check, 0)
        if len(group) <= allowed:
            continue
        ordered = sorted(group, key=lambda f: f.line)
        excess.extend(ordered[allowed:])
    return excess


def record(findings: list[Finding], root: Path, registry: Registry) -> Baseline:
    """Build a baseline from findings, keeping only checks that can block."""
    counts: dict[str, dict[str, int]] = {}
    tally: Counter = Counter()
    for finding in findings:
        check = registry.checks.get(finding.check)
        if check is None or check.advisory:
            continue
        tally[(_relative(finding.path, root), finding.check)] += 1
    for (key, check_id), number in tally.items():
        counts.setdefault(key, {})[check_id] = number
    return Baseline(counts=counts, root=root)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
