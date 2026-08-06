"""Check dispatch, and the one place exemptions are honored.

Individual checks never consult exemptions — doing it here means a new check
inherits the escape hatch, and the "exempt without a reason" rule cannot be
forgotten in one module and enforced in another.
"""

from __future__ import annotations

from functools import lru_cache

from ..findings import Finding
from ..registry import Registry, load
from ..source import SourceFile
from . import dangerous, duplication, errors, payloads, size, structure

# check id -> module exposing run(src, registry) -> list[Finding]
CHECK_MODULES = {
    "C-SIZE": size,
    "C-DUPE": duplication,
    "C-DATA": payloads,
    "C-ERR": errors,
    "C-DANGER": dangerous,
    "C-TYPE": structure,
    "C-TEST": structure,
    "C-STRUCT": structure,
    "C-DOC": structure,
}


@lru_cache(maxsize=1)
def default_registry() -> Registry:
    return load()


def run_checks(
    src: SourceFile,
    registry: Registry | None = None,
    only: list[str] | None = None,
) -> list[Finding]:
    """Run every applicable check and return findings with exemptions applied."""
    if src.language is None:
        return []
    reg = registry or default_registry()
    wanted = list(only) if only else list(CHECK_MODULES)

    findings: list[Finding] = []
    for module in _unique_modules(wanted):
        findings.extend(module.run(src, reg))

    selected = [f for f in findings if f.check in wanted]
    return sorted(_apply_exemptions(selected, src), key=lambda f: (f.line, f.check))


def _unique_modules(check_ids: list[str]):
    seen = []
    for check_id in check_ids:
        module = CHECK_MODULES.get(check_id)
        if module is not None and module not in seen:
            seen.append(module)
    return seen


def _apply_exemptions(findings: list[Finding], src: SourceFile) -> list[Finding]:
    """Drop exempted findings; convert reasonless exemptions into findings.

    A bare `exempt` is not a suppression — an escape hatch nobody has to justify
    is how a rule quietly stops applying.
    """
    kept = []
    for finding in findings:
        exemption = src.exemption_for(finding.check, finding.line)
        if exemption is None:
            kept.append(finding)
            continue
        if exemption.reason:
            continue
        kept.append(
            Finding(
                check=finding.check,
                article=finding.article,
                severity="warn",
                path=finding.path,
                line=exemption.line,
                message=f"{finding.check} exemption carries no reason",
                remedy=f"write `constitution: exempt {finding.check} — <why this one is correct inline>`",
            )
        )
    return kept
