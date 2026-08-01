"""Safe native command execution for coordinator adapters."""

import os
import re
import subprocess
from collections.abc import Mapping, Sequence

from manifest_agent.models import CommandResult

_REDACTIONS = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
        r"\s*[=:]\s*)[^\s,;]+"
    ),
    re.compile(r"\b(?:sk|ghp|glpat)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
)


def redact_text(value: str) -> str:
    """Remove common credential forms before native output is reportable."""
    redacted = value
    for pattern in _REDACTIONS:
        if pattern.groups:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class CommandRunner:
    """Execute an explicit argv without involving a command shell."""

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Return captured, redacted output for one validated argv."""
        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise TypeError("argv must be a sequence of strings, not a command string")
        command = tuple(argv)
        if not command or any(
            not isinstance(arg, str) or "\0" in arg for arg in command
        ):
            raise ValueError("argv must contain non-null strings")
        if env is not None and (
            not isinstance(env, Mapping)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in env.items()
            )
        ):
            raise TypeError("environment keys and values must be strings")

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=merged_env,
        )
        return CommandResult(
            command,
            completed.returncode,
            completed.stdout,
            redact_text(completed.stderr),
        )
