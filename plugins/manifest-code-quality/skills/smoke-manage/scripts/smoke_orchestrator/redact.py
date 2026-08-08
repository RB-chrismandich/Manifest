"""Redactor — central scrubbing of sensitive values from all output (T008).

Every output sink (console summary, JUnit failure text, logs) passes through
``scrub`` so a registered secret can never leak (FR-013, SC-006). Centralizing
redaction at the boundary means new sinks are covered by construction.
"""

from __future__ import annotations

_MASK = "***"


class Redactor:
    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def register(self, value: object) -> None:
        """Mark a resolved value as sensitive so it is masked everywhere."""
        if value is None:
            return
        s = str(value)
        if s:  # never register the empty string (would mask everything)
            self._secrets.add(s)

    def scrub(self, text: str) -> str:
        if not text:
            return text
        out = text
        # Longest-first so a secret that contains another is fully masked.
        for secret in sorted(self._secrets, key=len, reverse=True):
            out = out.replace(secret, _MASK)
        return out

    def __len__(self) -> int:
        return len(self._secrets)
