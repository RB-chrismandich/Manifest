"""Single truthful exit-status mapping."""

from __future__ import annotations


def executed_status(returncode: int, honors_status_contract: bool) -> str:
    if returncode == 0:
        return "PASS"
    if honors_status_contract and returncode == 3:
        return "BLOCKED"
    if honors_status_contract and returncode not in {0, 2}:
        return "BLOCKED"
    return "FAIL"
