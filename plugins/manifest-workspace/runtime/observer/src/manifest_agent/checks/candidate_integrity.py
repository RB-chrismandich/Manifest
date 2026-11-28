"""Detect candidate mutation before results are trusted."""

from __future__ import annotations

from .candidate import candidate_digest
from .models import Candidate


def identity_error(candidate: Candidate) -> str | None:
    return (
        None
        if candidate_digest(candidate.root) == candidate.digest
        else "candidate content changed during check execution"
    )
