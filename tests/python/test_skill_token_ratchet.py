"""No `[[skill:]]` token may reach a packaged file. The convention is retired.

Spec: `docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md`
§4 1.4 "Token gates", check 2 -- the packaged-artifact check, which asserts
**zero** `[[skill:` sequences in every packaged file and records a baseline of
106 occurrences across 45 files to drive to zero.

Phase 0 item 4 was decided 2026-08-27 as **option (b): retire the convention**.
All 106 tokens across 45 files were rewritten to qualified `bundle:skill`
commands and `docs/PLUGIN_RELEASE.md` now forbids the syntax, so the corpus is
zero and this IS that gate rather than a ratchet toward it. The second test
below -- which fails when the count falls -- now pins zero as the floor.

Neither resolver runs in production (`tools/skill_ref.py`'s only importer is a
test; `_bundle_expected_views()` never emits a transformed SKILL.md), so every
one of these tokens reaches the model as literal text today. A gate that only
rejected *unresolvable* tokens would pass the 92 well-formed ones while they
still ship literal, which is why this counts occurrences rather than validating
grammar.

Committed integers, following the `skill_policies.yml` idiom: an exogenous
number is the only thing a bulk edit cannot silently agree with.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS = REPO_ROOT / "plugins"

# ZERO as of 2026-08-27: the convention was retired, not merely ratcheted.
# All 106 tokens were rewritten to qualified `bundle:skill` commands and
# PLUGIN_RELEASE.md now forbids the syntax. At zero this stops being a
# ratchet and becomes the packaged-artifact gate the spec specified
# (section 4 1.4 token gate 2): assert NO `[[skill:` reaches a packaged file.
BASELINE_TOKENS = 0
BASELINE_FILES = 0

_TOKEN = re.compile(r"\[\[skill:")


def _token_census() -> tuple[int, int, dict[Path, int]]:
    per_file: dict[Path, int] = {}
    for path in sorted(PLUGINS.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        count = len(_TOKEN.findall(text))
        if count:
            per_file[path.relative_to(REPO_ROOT)] = count
    return sum(per_file.values()), len(per_file), per_file


def test_skill_token_corpus_does_not_grow() -> None:
    tokens, files, per_file = _token_census()

    assert tokens <= BASELINE_TOKENS, (
        f"[[skill:]] tokens grew {BASELINE_TOKENS} -> {tokens}. Every one ships "
        f"literal to the model -- no resolver runs in production. Rewrite the new "
        f"token as a qualified command instead of adding to the corpus.\n"
        + "\n".join(f"  {p}: {n}" for p, n in sorted(per_file.items()))
    )
    assert files <= BASELINE_FILES, (
        f"[[skill:]] citing files grew {BASELINE_FILES} -> {files}"
    )


def test_baseline_is_tightened_when_tokens_are_removed() -> None:
    """At zero this pins the floor rather than tightening a ratchet: it fails if
    BASELINE_TOKENS is ever raised above the real count, which is how an
    exemption for "just one" token would otherwise be granted quietly."""
    tokens, files, _ = _token_census()

    assert tokens == BASELINE_TOKENS, (
        f"[[skill:]] tokens fell {BASELINE_TOKENS} -> {tokens}. Lower "
        f"BASELINE_TOKENS to {tokens} in this file so the reduction is held."
    )
    assert files == BASELINE_FILES, (
        f"citing files fell {BASELINE_FILES} -> {files}. Lower BASELINE_FILES "
        f"to {files}."
    )
