"""CDDL — Critic-Driven Development Loop orchestrator package (feature 482).

Two-phase, critic-gated implementation loop: a bounded clarification gate
(both critics must emit structured completion signals) followed by a bounded
implement -> verify -> critique loop that stages changes only on dual explicit
approval. Entry point: ../cddl_loop.py.
"""

__version__ = "0.1.0"


class CddlError(Exception):
    """Base class for CDDL failures; message is operator-facing."""


class PreflightError(CddlError):
    """Refusal before any model call or state mutation (exit 6)."""


class AbortError(CddlError):
    """Unrecoverable mid-run failure: dead critic, deadline, signal (exit 7)."""
