"""Shared classification of native adapter command outcomes."""

from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import redact_text


def _classified_diagnostic_result(
    harness: str, tier: CapabilityTier, diagnostic: str
) -> HarnessResult:
    if tier is CapabilityTier.REQUIRED:
        return HarnessResult(harness, ResultState.BLOCKED, (), {}, errors=(diagnostic,))
    if tier is CapabilityTier.DEFAULT:
        return HarnessResult(
            harness, ResultState.DEGRADED, (), {}, errors=(diagnostic,)
        )
    return HarnessResult(harness, ResultState.READY, (), {}, warnings=(diagnostic,))


def _unselected_optional_result(harness: str) -> HarnessResult:
    return HarnessResult(
        harness,
        ResultState.BLOCKED,
        (),
        {},
        errors=("optional native command was not explicitly selected",),
    )


def _command_diagnostic(command: CommandResult) -> str:
    parts = [f"native command exited {command.returncode}"]
    stdout = redact_text(command.stdout.strip())
    stderr = redact_text(command.stderr.strip())
    if stdout:
        parts.append(f"stdout: {stdout}")
    if stderr:
        parts.append(f"stderr: {stderr}")
    return "; ".join(parts)
