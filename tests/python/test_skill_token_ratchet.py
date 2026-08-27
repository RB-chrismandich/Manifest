"""`[[skill:]]` tokens must not grow while the convention's fate is undecided.

Spec: `docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md`
§4 1.4 "Token gates", check 2 -- the packaged-artifact check, which asserts
**zero** `[[skill:` sequences in every packaged file and records a baseline of
106 occurrences across 45 files to drive to zero.

That gate cannot land as written until the corpus is actually zero, and Phase 0
item 4 is still an open fork: (a) wire a renderer into packaging, or (b) retire
the convention and rewrite every token. This ratchet is the decision-neutral
half that can land now -- it does not care which option is chosen, only that
the corpus stops accumulating while nobody has chosen.

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

# Measured 2026-08-26 on main, unchanged from the PR #810 head measurement
# recorded in the tracking issue. LOWER these when tokens are removed; a
# ratchet that is never tightened is just a comment.
BASELINE_TOKENS = 106
BASELINE_FILES = 45

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
    """The other half of a ratchet. Without this the baseline drifts upward in
    effect -- removals buy headroom for future additions instead of being
    locked in."""
    tokens, files, _ = _token_census()

    assert tokens == BASELINE_TOKENS, (
        f"[[skill:]] tokens fell {BASELINE_TOKENS} -> {tokens}. Lower "
        f"BASELINE_TOKENS to {tokens} in this file so the reduction is held."
    )
    assert files == BASELINE_FILES, (
        f"citing files fell {BASELINE_FILES} -> {files}. Lower BASELINE_FILES "
        f"to {files}."
    )
