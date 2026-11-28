"""Declarative local shared-check engine."""

from .aggregate import aggregate_results
from .candidate import CandidateBlockedError, candidate_digest, materialize_candidate
from .models import Candidate, CheckResult, CheckSpec
from .registry import load_registry, resolve_checks
from .runner import execute_check, run_profile

__all__ = [
    "Candidate",
    "CandidateBlockedError",
    "CheckResult",
    "CheckSpec",
    "aggregate_results",
    "candidate_digest",
    "execute_check",
    "load_registry",
    "materialize_candidate",
    "resolve_checks",
    "run_profile",
]
