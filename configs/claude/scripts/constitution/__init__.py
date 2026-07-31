"""Code Constitution — the checkable half of the pre-write doctrine.

Public surface:
    registry.load()          read code_constitution.yml into declared records
    source.SourceFile.load() parse one file once, for every check to share
    checks.run_checks()      run the applicable checks, exemptions applied
    findings.render_*()      the three output shapes (text, json, context)

Prose lives in references/code-constitution.md; this package only implements
what a machine can prove. Articles with `checks: []` are judgement calls the
pre-write hook surfaces and no checker pretends to verify.
"""

from .findings import Finding, render_context, render_json, render_text, worst
from .registry import Registry, RegistryError, load
from .source import SourceFile

__all__ = [
    "Finding",
    "Registry",
    "RegistryError",
    "SourceFile",
    "load",
    "render_context",
    "render_json",
    "render_text",
    "worst",
]
